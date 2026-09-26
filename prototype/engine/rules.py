"""Layer 1 (deterministic rules) and layer 2 (detectors) for the Senti prototype.

Each check returns a Decision or None ("not settled here, go to the next layer").
"""
from __future__ import annotations

import base64, math, os, re, shlex
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

HOME = str(Path.home())


@dataclass
class Decision:
    verdict: str  # allow | ask | block
    reason: str
    layer: str
    rule: str = ""


# ---------------------------------------------------------------- paths
SENSITIVE_PATTERNS = [
    r"/\.ssh(/|$)", r"/\.aws(/|$)", r"/\.gnupg(/|$)", r"/\.config/gcloud(/|$)", r"/\.kube/config",
    r"/\.docker/config\.json", r"/\.netrc$", r"/\.npmrc$", r"/\.pypirc$", r"\.pem$", r"\.p12$", r"id_(rsa|ed25519|ecdsa)",
    r"/Library/Keychains(/|$)", r"login\.keychain", r"/Library/Cookies(/|$)",
    r"/Library/Application Support/(Google/Chrome|BraveSoftware|Firefox|Microsoft Edge)", r"/Library/Safari(/|$)",
    r"/Library/Messages(/|$)", r"/\.password-store(/|$)", r"/\.bash_history$", r"/\.zsh_history$",
]
SECRET_FILE_PATTERNS = [r"(^|/)\.env(\.[\w-]+)?$", r"(^|/)secrets?\.(ya?ml|json)$", r"(^|/)credentials(\.json)?$"]
GUARD_PATTERNS = [r"/\.claude/settings(\.local)?\.json$", r"/\.cursor/hooks\.json$", r"/Senti(/|$)", r"/\.senti(/|$)"]
PERSISTENCE_PATTERNS = [r"/Library/LaunchAgents/", r"/Library/LaunchDaemons/", r"/\.zshrc$", r"/\.bash_profile$", r"/\.profile$"]
PERSONAL_DIRS = ["Documents", "Desktop", "Pictures", "Movies", "Music", "Downloads", "Library"]
BUILD_ARTIFACTS = {"build", "dist", "node_modules", ".next", "__pycache__", "target", "coverage", ".cache", "out",
                   ".pytest_cache", ".turbo", ".parcel-cache"}


def expand(p: str, cwd: str) -> str:
    p = p.strip().strip("'\"").replace("$HOME", HOME).replace("${HOME}", HOME)
    if p.startswith("~"):
        p = HOME + p[1:]
    if not p.startswith("/"):
        p = os.path.join(cwd, p)
    return os.path.normpath(p)


def match_any(path: str, patterns) -> bool:
    return any(re.search(p, path) for p in patterns)


def classify_path(path: str) -> str:
    if match_any(path, GUARD_PATTERNS):
        return "guard"
    if match_any(path, SENSITIVE_PATTERNS):
        return "sensitive"
    if match_any(path, SECRET_FILE_PATTERNS):
        return "secret_file"
    if match_any(path, PERSISTENCE_PATTERNS):
        return "persistence"
    return "normal"


def inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


# ---------------------------------------------------------------- detectors (layer 2)
SECRET_VALUE_PATTERNS = {
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "private_key": r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{36}",
    "openai_key": r"sk-(proj-)?[A-Za-z0-9_-]{20,}",
    "anthropic_key": r"sk-ant-[A-Za-z0-9_-]{20,}",
    "slack_token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "stripe_key": r"sk_live_[A-Za-z0-9]{20,}",
}


def entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    return -sum(n / len(s) * math.log2(n / len(s)) for n in counts.values())


def find_secrets(text: str) -> list[str]:
    hits = [name for name, pat in SECRET_VALUE_PATTERNS.items() if re.search(pat, text)]
    for m in re.finditer(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"]?([^\s'\"]{16,})", text):
        if entropy(m.group(2)) > 3.5:
            hits.append("high_entropy_" + m.group(1).lower())
    return hits


B64_BLOB = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def decode_hidden(cmd: str) -> list[str]:
    """Unwrap base64 blobs so hidden commands get checked by the same rules."""
    out = []
    for blob in B64_BLOB.findall(cmd):
        try:
            txt = base64.b64decode(blob + "=" * (-len(blob) % 4)).decode("utf-8")
            if txt.isprintable() or "\n" in txt:
                out.append(txt)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- shell parsing
NET_TOOLS = {"curl", "wget", "nc", "ncat", "netcat", "scp", "rsync", "ftp", "sftp", "ssh", "telnet", "socat"}
SAFE_PROGRAMS = {"ls", "pwd", "echo", "wc", "which", "whoami", "date", "tree", "diff", "sort", "uniq", "true", "file",
                 "grep", "rg", "head", "tail", "cat", "less", "stat", "du", "basename", "dirname", "jq", "sed", "awk",
                 "tsc", "eslint", "prettier", "mkdir", "touch", "cp", "mv", "cd"}
SAFE_SUBCOMMANDS = {
    "git": {"status", "diff", "log", "show", "branch", "add", "commit", "checkout", "switch", "fetch", "pull", "stash",
            "restore", "rev-parse", "remote", "tag", "merge", "rebase"},
    "npm": {"test", "run", "ci", "ls", "outdated", "audit", "start", "exec"},
    "pnpm": {"test", "run", "install", "ls", "build", "dev", "lint"},
    "yarn": {"test", "run", "install", "build", "dev", "lint"},
    "cargo": {"build", "test", "check", "clippy", "fmt", "run"},
    "go": {"build", "test", "vet", "fmt", "run", "mod"},
    "make": None, "pytest": None, "node": {"--version", "-v"}, "python3": {"-m"}, "python": {"-m"},
}
SAFE_PY_MODULES = {"pytest", "unittest", "mypy", "black", "ruff", "pip"}
SCRIPT_RUNNERS = {"python", "python3", "node", "bash", "sh", "zsh", "ruby", "perl", "deno", "bun", "ts-node", "tsx"}


def split_segments(cmd: str) -> list[list[str]]:
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    segs, cur = [], []
    try:
        for tok in lexer:
            if tok in {";", "&&", "||", "|", "&"}:
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append(tok)
    except ValueError:
        return []
    if cur:
        segs.append(cur)
    return segs


def program(seg: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(seg) and (re.match(r"^\w+=", seg[i]) or seg[i] in {"sudo", "env", "nohup", "time"}):
        i += 1
    if i >= len(seg):
        return "", []
    return os.path.basename(seg[i]), seg[i + 1:]


HARD_DENY_CMD = [
    (r"(curl|wget)[^|;&]*\|\s*(sudo\s+)?(ba|z)?sh\b", "Downloads a script from the internet and runs it immediately"),
    (r"/dev/tcp/|\bnc\b[^|;&]*\s-e\s|\bncat\b[^|;&]*--exec|socat[^|;&]*exec:", "Opens a remote shell (a backdoor) to another computer"),
    (r"base64\s+(-d|--decode|-D)[^|;&]*\|\s*(ba|z)?sh\b", "Runs a hidden (encoded) command"),
    (r"\bdd\b[^;&|]*\bof=/dev/(r?disk|sd|nvme)", "Overwrites a whole disk"),
    (r"\bmkfs(\.\w+)?\b|\bdiskutil\s+(erase|zero|secureErase)", "Erases a disk"),
    (r"chmod\s+(-R\s+)?[0-7]?777\s+/(\s|$)", "Makes every file on the system writable by anyone"),
    (r"\bsecurity\s+(dump-keychain|find-generic-password\s[^;&|]*-w|find-internet-password)", "Reads saved passwords from the macOS Keychain"),
    (r"crontab\b[^;]*(curl|wget|nc)\b", "Installs a scheduled task that contacts the internet"),
    (r"\bcsrutil\s+disable|spctl\s+--master-disable", "Turns off macOS security protections"),
]


def check_bash(cmd: str, cwd: str, project: str, depth: int = 0) -> tuple[Decision | None, dict]:
    """Returns (decision or None, facts for later layers)."""
    facts = {"scripts": [], "net": False, "reads_sensitive": False, "unknown": []}
    for pat, why in HARD_DENY_CMD:
        if re.search(pat, cmd):
            return Decision("block", why, "L1-rules", pat), facts
    for hidden in decode_hidden(cmd) if depth == 0 else []:
        d, _ = check_bash(hidden, cwd, project, depth + 1)
        if d and d.verdict == "block":
            return Decision("block", "Runs a hidden (encoded) command: " + d.reason.lower(), "L2-detectors", "decoded"), facts
    segs = split_segments(cmd)
    if not segs:
        return None, facts
    all_safe = True
    for seg in segs:
        prog, args = program(seg)
        paths = [expand(a.lstrip("@").split("=", 1)[-1], cwd) for a in args
                 if a.startswith(("/", "~", "./", "../", "$HOME", "@")) or ("/" in a and not a.startswith("http"))
                 or re.search(r"\.env\b|id_rsa|credentials", a)]
        kinds = {classify_path(p) for p in paths}
        if kinds & {"sensitive", "secret_file"}:
            facts["reads_sensitive"] = True
        if prog in NET_TOOLS:
            urls = [a for a in args if a.startswith("http")]
            if urls and all(re.match(r"https?://(localhost|127\.0\.0\.1)([:/]|$)", u) for u in urls):
                continue  # talking to a local dev server
            facts["net"] = True
            all_safe = False
            continue
        if "guard" in kinds and prog not in {"cat", "ls", "head", "grep", "stat"}:
            return Decision("block", "Tries to change or switch off Senti's own protection", "L1-rules", "guard_path"), facts
        if prog == "rm":
            targets = [p for p in paths] or [expand(a, cwd) for a in args if not a.startswith("-")]
            for t in targets:
                if t in {"/", HOME} or any(t == os.path.join(HOME, d) or inside(t, os.path.join(HOME, d)) and not inside(t, project)
                                           for d in PERSONAL_DIRS):
                    return Decision("block", f"Deletes your personal files ({t.replace(HOME, '~')})", "L1-rules", "rm_personal"), facts
                if not (inside(t, project) and (os.path.basename(t) in BUILD_ARTIFACTS)):
                    all_safe = False
            continue
        if prog in SCRIPT_RUNNERS:
            script = next((a for a in args if not a.startswith("-")), None)
            if prog in {"python", "python3"} and args[:1] == ["-m"] and len(args) > 1 and args[1] in SAFE_PY_MODULES:
                if args[1] == "pip":
                    all_safe = False
                continue
            if "-c" in args or "-e" in args:
                all_safe = False
                continue
            if script:
                facts["scripts"].append(expand(script, cwd))
            all_safe = False
            continue
        if prog.startswith("./") or (seg and seg[0].startswith(("./", "/")) and prog not in SAFE_PROGRAMS):
            facts["scripts"].append(expand(seg[0], cwd))
            all_safe = False
            continue
        if prog in SAFE_PROGRAMS:
            if kinds & {"sensitive", "secret_file", "persistence"} or any(not inside(p, project) and p != "/dev/null" for p in paths):
                all_safe = False
            continue
        if prog in SAFE_SUBCOMMANDS:
            subs = SAFE_SUBCOMMANDS[prog]
            first = next((a for a in args if not a.startswith("-")), "")
            if prog == "git" and first == "push":
                all_safe = False
            elif subs is not None and first not in subs and (args[:1] and args[0] not in subs):
                all_safe = False
            elif prog in {"npm", "pnpm", "yarn"} and first in {"install", "i", "add"} and len([a for a in args if not a.startswith("-")]) > 1:
                all_safe = False  # installing a named package: supply-chain check
            continue
        facts["unknown"].append(prog)
        all_safe = False
    if facts["net"] and facts["reads_sensitive"]:
        return Decision("block", "Sends a secret or private file to the internet", "L1-rules", "taint_net"), facts
    if all_safe:
        return Decision("allow", "Routine development command", "L1-rules", "safe_command"), facts
    return None, facts


SAFE_DOMAINS = {"docs.python.org", "developer.mozilla.org", "github.com", "api.github.com", "pypi.org", "npmjs.com",
                "www.npmjs.com", "stackoverflow.com", "developer.apple.com", "react.dev", "nodejs.org", "docs.anthropic.com",
                "learn.microsoft.com", "go.dev", "doc.rust-lang.org", "zod.dev", "tailwindcss.com"}


def check_action(tool: str, inp: dict, cwd: str, project: str) -> tuple[Decision | None, dict]:
    facts: dict = {"scripts": []}
    if tool == "Bash":
        return check_bash(inp.get("command", ""), cwd, project)
    if tool in {"Read", "Grep", "Glob", "LS", "NotebookRead"}:
        p = expand(inp.get("file_path") or inp.get("path") or cwd, cwd)
        kind = classify_path(p)
        if kind == "sensitive":
            return Decision("block", f"Reads a private key or credential file ({p.replace(HOME, '~')})", "L1-rules", "read_sensitive"), facts
        if kind == "secret_file":
            return Decision("ask", f"Reads a file with passwords/API keys ({os.path.basename(p)})", "L1-rules", "read_secret_file"), facts
        if inside(p, project):
            if tool == "Read" and re.search(r"(?i)(config|secret|credential|token|key|passw|\.ya?ml$|\.ini$|\.toml$|\.properties$)", os.path.basename(p)):
                return None, {"path": p, "in_project": True}  # config-like file: let the LLM check it fits the task
            return Decision("allow", "Reads or searches project files", "L1-rules", "read_project"), facts
        return None, {"path": p, "in_project": False}
    if tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        p = expand(inp.get("file_path", ""), cwd)
        kind = classify_path(p)
        content = inp.get("content", "") + inp.get("new_string", "")
        if kind == "guard":
            return Decision("block", "Tries to change or switch off Senti's own protection", "L1-rules", "guard_path"), facts
        if kind == "sensitive":
            return Decision("block", f"Changes your keys or credentials ({p.replace(HOME, '~')})", "L1-rules", "write_sensitive"), facts
        if kind == "persistence":
            return Decision("ask", "Makes a program start automatically when you log in", "L1-rules", "persistence"), facts
        secrets = find_secrets(content)
        if secrets and kind != "secret_file":
            return Decision("ask", f"Writes what looks like a real secret ({', '.join(secrets)}) into a code file", "L2-detectors", "secret_in_content"), facts
        if inside(p, project):
            return Decision("allow", "Edits a file inside the project", "L1-rules", "edit_project"), facts
        return None, facts
    if tool in {"WebFetch", "WebSearch"}:
        if tool == "WebSearch":
            return Decision("allow", "Web search", "L1-rules", "search"), facts
        host = urlparse(inp.get("url", "")).hostname or ""
        if host in SAFE_DOMAINS or any(host.endswith("." + d) for d in SAFE_DOMAINS):
            return Decision("allow", "Reads documentation from a known site", "L1-rules", "safe_domain"), facts
        if re.fullmatch(r"[\d.]+", host):
            return Decision("ask", f"Fetches content from a raw IP address ({host})", "L1-rules", "ip_url"), facts
        return None, facts
    if tool.startswith("mcp__"):
        return None, facts
    return None, facts
