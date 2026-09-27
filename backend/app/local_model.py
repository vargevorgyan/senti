"""The private model on this server (the bundled Ollama container): what is downloaded, downloads, and whether it fits.

The admin panel uses this to offer "On this server" next to "Cloud API". Everything here only talks to the Ollama
address from settings (never a URL from the request), and model names are checked before they reach Ollama.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

import httpx

from .config import settings

# Models known to work as a judge, smallest first. RAM is what the Ollama container needs with the model loaded.
RECOMMENDED = [
    {"model": "qwen2.5:3b", "ram_gb": 3.0, "download_gb": 1.9, "note": "Fast on a CPU; fine for clear cases"},
    {"model": "qwen3:4b-instruct", "ram_gb": 4.0, "download_gb": 2.5, "note": "Better judgment, still CPU-friendly"},
    {"model": "qwen2.5:7b", "ram_gb": 6.0, "download_gb": 4.7, "note": "Noticeably better; wants 8 GB free or a GPU"},
]
MODEL_NAME = re.compile(r"[a-z0-9][a-z0-9._/-]{0,79}(:[a-z0-9._-]{1,40})?")

# one download at a time; progress is kept in memory (a restart forgets it, Ollama keeps what it finished)
_pull: dict = {}
_task: asyncio.Task | None = None


def base_url() -> str:
    return settings.local_model_url.rstrip("/").removesuffix("/v1")


def is_local(url: str) -> bool:
    """Is this endpoint the bundled private model (as opposed to a cloud API)?"""
    return url.rstrip("/").removesuffix("/v1") == base_url()


def memory() -> dict:
    """This server's memory (the container sees the host's /proc/meminfo)."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) / 1024 / 1024
        return {"total_gb": round(info["MemTotal"], 1), "available_gb": round(info.get("MemAvailable", 0), 1)}
    except (OSError, KeyError, ValueError):
        return {}


async def status() -> dict:
    out: dict = {"url": base_url() + "/v1", "memory": memory(), "recommended": RECOMMENDED,
                 "pulling": dict(_pull) if _pull else None}
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(base_url() + "/api/tags")
            r.raise_for_status()
        out["running"] = True
        out["models"] = [{"name": m.get("name", ""), "size_gb": round((m.get("size") or 0) / 1e9, 1)}
                         for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError) as e:
        out["running"] = False
        out["models"] = []
        out["error"] = type(e).__name__
    return out


async def _run_pull(model: str) -> None:
    _pull.update(model=model, status="starting", completed=0, total=0, started=time.time(), error="")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=600)) as c:
            async with c.stream("POST", base_url() + "/api/pull", json={"model": model, "stream": True}) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    ev = json.loads(line)
                    if ev.get("error"):
                        raise RuntimeError(ev["error"])
                    _pull["status"] = ev.get("status", _pull["status"])
                    if ev.get("total"):
                        _pull["total"], _pull["completed"] = ev["total"], ev.get("completed", 0)
        _pull.update(status="success", done=True)
    except Exception as e:  # shown in the panel; the admin can try again
        _pull.update(status="failed", error=f"{type(e).__name__}: {str(e)[:200]}", done=True)


def start_pull(model: str) -> dict:
    global _task
    if not MODEL_NAME.fullmatch(model):
        raise ValueError("model names look like qwen2.5:3b")
    if _task and not _task.done():
        raise RuntimeError(f"already downloading {_pull.get('model')}; wait for it to finish")
    _pull.clear()
    _task = asyncio.get_running_loop().create_task(_run_pull(model))
    return {"model": model, "status": "starting"}
