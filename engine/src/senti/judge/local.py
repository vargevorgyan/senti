"""Local judge: Qwen3-4B-Instruct (4-bit) on MLX with the measured speed tricks.

- Prefix KV cache: the fixed system prompt is processed once; each request feeds only its own tokens.
- Logit verdict: the prompt ends with '{"verdict": "' and we read p(allow/ask/block) from one forward pass.
- Safety bias: allow only if p(allow) >= threshold.
- Reason generated only for ask/block.
- Lazy load in a background thread; unload after idle to give memory back.
"""
from __future__ import annotations

import threading
import time

from .base import SYSTEM_PROMPT, VERDICTS, JudgeResult, biased_verdict, render_prompt


class LocalJudge:
    def __init__(self, repo: str, allow_threshold: float = 0.6, unload_after_idle_s: int = 900):
        self.repo = repo
        self.allow_threshold = allow_threshold
        self.unload_after_idle_s = unload_after_idle_s
        self.lock = threading.Lock()
        self.model = None
        self.state = "unloaded"  # unloaded | loading | ready | error | unavailable
        self.error = ""
        self.last_used = 0.0
        self._loaded = threading.Event()
        try:
            import mlx.core  # noqa: F401
            import mlx_lm  # noqa: F401
        except Exception as e:  # MLX missing (not Apple Silicon / extra not installed)
            self.state, self.error = "unavailable", f"MLX not installed: {e}"

    # ---------------------------------------------------------------- lifecycle
    def start_loading(self) -> None:
        if self.state in {"unloaded", "error"}:
            self.state = "loading"
            self._loaded.clear()
            threading.Thread(target=self._load, daemon=True, name="senti-judge-load").start()

    def _load(self) -> None:
        try:
            import mlx.core as mx
            from mlx_lm import load
            from mlx_lm.models.cache import make_prompt_cache

            t = time.perf_counter()
            model, tok = load(self.repo)
            marker = "§§§"
            rendered = tok.apply_chat_template([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": marker}],
                                               add_generation_prompt=True, tokenize=False)
            pre, post = rendered.split(marker)
            with self.lock:
                self.mx, self.tok, self.model = mx, tok, model
                self.post_str = post + '{"verdict": "'
                self.verdict_ids = [tok.encode(v)[0] for v in VERDICTS]
                self.cache = make_prompt_cache(model)
                mx.eval(model(mx.array(tok.encode(pre))[None], cache=self.cache))
                self.load_s = time.perf_counter() - t
                self.state = "ready"
                self.last_used = time.time()
        except Exception as e:
            self.state, self.error = "error", str(e)
        finally:
            self._loaded.set()

    def maybe_unload(self) -> None:
        if self.state == "ready" and self.unload_after_idle_s and time.time() - self.last_used > self.unload_after_idle_s:
            with self.lock:
                self.model = self.cache = None
                self.state = "unloaded"
            import gc
            gc.collect()

    @property
    def available(self) -> bool:
        return self.state not in {"unavailable"}

    def wait_ready(self, timeout: float) -> bool:
        if self.state == "ready":
            return True
        if self.state == "unavailable":
            return False
        self.start_loading()
        self._loaded.wait(timeout)
        return self.state == "ready"

    # ---------------------------------------------------------------- inference
    def _forward(self, ids):
        return self.model(self.mx.array(ids)[None], cache=self.cache)[0, -1]

    def decide(self, task: str, action: dict, script: str | None = None, instructions: str = "", facts: dict | None = None,
               want_reason: bool = True, timeout: float = 20.0) -> JudgeResult:
        if not self.wait_ready(timeout):
            return JudgeResult("ask", "", source="local", error=self.error or f"local judge {self.state}")
        from mlx_lm.models.cache import trim_prompt_cache
        with self.lock:
            mx = self.mx
            t0 = time.perf_counter()
            user_ids = self.tok.encode(render_prompt(task, action, script, instructions, facts) + self.post_str)
            fed = len(user_ids)
            try:
                logits = self._forward(user_ids)
                probs = mx.softmax(logits[mx.array(self.verdict_ids)].astype(mx.float32)).tolist()
                p = dict(zip(VERDICTS, probs))
                verdict = biased_verdict(p, self.allow_threshold)
                reason = ""
                if want_reason and verdict != "allow":
                    nxt = self.tok.encode(verdict + '", "reason": "')
                    logits = self._forward(nxt)
                    fed += len(nxt)
                    out: list[int] = []
                    for _ in range(48):
                        tid = int(mx.argmax(logits).item())
                        if tid in self.tok.eos_token_ids:
                            break
                        out.append(tid)
                        if '"' in self.tok.decode(out):
                            break
                        logits = self._forward([tid])
                        fed += 1
                    reason = self.tok.decode(out).split('"')[0].strip()
            finally:
                trim_prompt_cache(self.cache, fed)
            self.last_used = time.time()
            return JudgeResult(verdict, reason, {k: round(v, 3) for k, v in p.items()}, "local", self.repo,
                               round((time.perf_counter() - t0) * 1000))

    def generate(self, prompt: str, max_tokens: int = 160) -> str:
        """Free-form generation with a fresh cache (used by the task scope contract)."""
        if not self.wait_ready(20):
            return ""
        from mlx_lm import generate
        with self.lock:
            msgs = [{"role": "user", "content": prompt}]
            text = self.tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
            self.last_used = time.time()
            return generate(self.model, self.tok, prompt=text, max_tokens=max_tokens, verbose=False)
