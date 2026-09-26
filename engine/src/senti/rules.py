"""Layer 1 (deterministic rules) and layer 2 (detectors).

Every check returns a Decision or None ("not settled here, go to the next layer") plus *facts* that later
layers use (does it touch the network? read secrets? run a script?). Hard denies decided here can never be
overridden by a profile or by the LLM judge.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import shlex
from pathlib import Path
from urllib.parse import urlparse

from .models import Decision

HOME = str(Path.home())


def _senti_home() -> str:
    return os.environ.get("SENTI_HOME", os.path.join(HOME, ".senti"))


# ---------------------------------------------------------------- paths
SENSITIVE_PATTERNS = [
    r"/\.ssh(/|$)", r"/\.aws(/|$)", r"/\.gnupg(/|$)", r"/\.config/gcloud(/|$)", r"/\.kube/config",
    r"/\.docker/config\.json", r"/\.netrc$", r"/\.npmrc$", r"/\.pypirc$", r"\.pem$", r"\.p12$", r"\.key$",
    r"id_(rsa|ed25519|ecdsa|dsa)", r"/Library/Keychains(/|$)", r"login\.keychain", r"/Library/Cookies(/|$)",
    r"/Library/Application Support/(Google/Chrome|BraveSoftware|Firefox|Microsoft Edge|Arc)", r"/Library/Safari(/|$)",
    r"/Library/Messages(/|$)", r"/\.password-store(/|$)", r"/\.bash_history$", r"/\.zsh_history$",
    r"/\.codex/auth\.json$", r"/\.claude/\.credentials\.json$", r"/\.config/gh/hosts\.yml$",
]
SECRET_FILE_PATTERNS = [r"(^|/)\.env(\.[\w.-]+)?$", r"(^|/)secrets?\.(ya?ml|json|toml)$", r"(^|/)credentials(\.json)?$",
                        r"(^|/)\.dev\.vars$", r"(^|/)service[-_]account.*\.json$"]
GUARD_PATTERNS = [
    r"/\.claude/settings(\.local)?\.json$", r"/\.cursor/hooks\.json$", r"/\.codex/config\.toml$", r"/\.codex/hooks\.json$",
    r"/\.config/opencode/plugins?/", r"/\.opencode/plugins?/", r"/\.config/opencode/opencode\.jsonc?$",
    r"/Senti(/|$)", r"/\.senti(/|$)", r"/LaunchAgents/am\.tumo\.senti",
]
PERSISTENCE_PATTERNS = [r"/Library/LaunchAgents/", r"/Library/LaunchDaemons/", r"/\.zshrc$", r"/\.zprofile$",
                        r"/\.bashrc$", r"/\.bash_profile$", r"/\.profile$", r"/\.git/hooks/", r"/etc/"]
RUN_LATER_PATTERNS = [r"(^|/)package\.json$", r"(^|/)Makefile$", r"(^|/)\.github/workflows/", r"(^|/)\.gitlab-ci\.yml$",
                      r"(^|/)\.husky/", r"(^|/)setup\.py$", r"(^|/)pyproject\.toml$"]
PERSONAL_DIRS = ["Documents", "Desktop", "Pictures", "Movies", "Music", "Downloads", "Library", "Public"]
BUILD_ARTIFACTS = {"build", "dist", "node_modules", ".next", "__pycache__", "target", "coverage", ".cache", "out",
                   ".pytest_cache", ".turbo", ".parcel-cache", ".venv", "venv", ".mypy_cache", ".ruff_cache", "tmp"}


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
    if match_any(path, GUARD_PATTERNS) or inside(path, _senti_home()):
        return "guard"
    if match_any(path, SENSITIVE_PATTERNS):
        return "sensitive"
    if match_any(path, SECRET_FILE_PATTERNS):
        return "secret_file"
    if match_any(path, PERSISTENCE_PATTERNS):
        return "persistence"
    return "normal"


def inside(path: str, root: str) -> bool:
    root = root.rstrip("/") or "/"
    return path == root or path.startswith(root + "/")


def project_root(cwd: str) -> str:
    """Nearest git root above cwd, else cwd itself."""
    p = Path(os.path.abspath(cwd)) if cwd else Path.cwd()
    for d in [p, *p.parents]:
        if (d / ".git").exists():
            return str(d)
        if str(d) == HOME:
            break
    return str(p)


def short(p: str) -> str:
    return p.replace(HOME, "~")


# ---------------------------------------------------------------- detectors (layer 2)
SECRET_VALUE_PATTERNS = {
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "private key": r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{36}",
    "OpenAI key": r"sk-(proj-)?[A-Za-z0-9_-]{20,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9_-]{20,}",
    "Slack token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "Stripe key": r"sk_live_[A-Za-z0-9]{20,}",
    "Google API key": r"AIza[0-9A-Za-z_-]{35}",
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
            hits.append("high-entropy " + m.group(1).lower())
    return sorted(set(hits))


def redact(text: str) -> str:
    """Replace secret-looking values before content leaves the machine (corporate judge)."""
    for pat in SECRET_VALUE_PATTERNS.values():
        text = re.sub(pat, "[REDACTED]", text)
    text = re.sub(r"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"]?)([^\s'\"]{6,})", r"\1[REDACTED]", text)
    return text


B64_BLOB = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def decode_hidden(cmd: str) -> list[str]:
    """Unwrap base64 / hex blobs so hidden commands get checked by the same rules."""
    out = []
    for blob in B64_BLOB.findall(cmd):
        try:
            txt = base64.b64decode(blob + "=" * (-len(blob) % 4)).decode("utf-8")
            if txt.isprintable() or "\n" in txt:
                out.append(txt)
        except Exception:
            pass
    for blob in re.findall(r"(?:\\x[0-9a-fA-F]{2}){6,}", cmd):
        try:
            out.append(bytes.fromhex(blob.replace("\\x", "")).decode("utf-8"))
        except Exception:
            pass
    return out


# Static scan of script / code content (a script is just more commands)
SCRIPT_SENSITIVE = re.compile(r"\.ssh|\.aws/credentials|\.aws['\"]|id_rsa|id_ed25519|\.env\b|Keychains|Cookies|\.gnupg|"
                              r"login\.keychain|\.netrc|\.npmrc|\.pypirc|\.kube/config|find-generic-password")
SCRIPT_NET = re.compile(r"requests\.(post|put|request|patch)|urlopen\(|urllib\.request|fetch\(|axios\.|http\.client|"
                        r"socket\.connect|\bcurl\s|\bwget\s|httpx\.(post|put|request|Client|AsyncClient)|"
                        r"XMLHttpRequest|net\.connect|smtplib|ftplib|paramiko|\bnc\s")
SCRIPT_WIPE = re.compile(
    r"(rmtree|rm\s+-[a-zA-Z]*r[a-zA-Z]*f?|rm\s+-[a-zA-Z]*f[a-zA-Z]*r|unlink|os\.remove|fs\.rm|rimraf|shutil\.move)"
    r"[^\n]{0,160}(~|expanduser|HOME|homedir\(\)|Path\.home)[^\n]{0,80}"
    r"(Documents|Desktop|Pictures|Movies|Music|Downloads|Library)|"
    r"(Documents|Desktop|Pictures|Movies|Music|Downloads)['\"][^\n]{0,120}\n?[^\n]{0,200}(rmtree|os\.remove|unlink|fs\.rm)")
SCRIPT_OBFUSCATION = re.compile(r"(exec|eval)\s*\(\s*(base64|codecs|bytes\.fromhex|zlib|marshal|compile\(|requests\.get|urlopen)|"
                                r"__import__\(['\"](base64|zlib|marshal)|Function\(\s*atob|eval\(\s*atob")


def scan_code(text: str) -> Decision | None:
    """Detectors over script content. Returns a block/ask decision or None."""
    sens, net = SCRIPT_SENSITIVE.search(text), SCRIPT_NET.search(text)
    if sens and net:
        return Decision("block", "The script reads secret files and sends data to the internet", "L2-detectors",
                        "script_taint", severity="critical")
    if SCRIPT_WIPE.search(text):
        return Decision("block", "The script deletes your personal folders (Documents, Desktop, Pictures...)", "L2-detectors",
                        "script_wipe", severity="critical")
    for pat, why in HARD_DENY_CMD:
        if re.search(pat, text):
            return Decision("block", "The script " + why[0].lower() + why[1:], "L2-detectors", "script_rule", severity="critical")
    if re.search(r"(?i)(security|guard|reviewer|senti|safety)[^\n]{0,60}(answer|respond|reply|verdict|say)[^\n]{0,20}"
                 r"['\"]?allow", text) or re.search(r"(?i)ignore (all |any )?(previous|prior) instructions", text):
        return Decision("block", "The script contains text that tries to talk the security check into allowing it", "L2-detectors",
                        "reviewer_injection", severity="critical")
    if SCRIPT_OBFUSCATION.search(text):
        return Decision("ask", "The script runs hidden or downloaded code", "L2-detectors", "script_obfuscation", severity="warning")
    return None


# ---------------------------------------------------------------- shell parsing
DB_CLIENTS = {"psql", "mysql", "mariadb", "redis-cli", "mongo", "mongosh", "sqlcmd", "clickhouse-client", "cqlsh", "pg_dump",
              "mysqldump", "mongodump"}
NET_TOOLS = {"curl", "wget", "nc", "ncat", "netcat", "scp", "rsync", "ftp", "sftp", "ssh", "telnet", "socat", "http", "https"}
SAFE_PROGRAMS = {"ls", "pwd", "echo", "wc", "which", "whoami", "date", "tree", "diff", "sort", "uniq", "true", "false", "file",
                 "grep", "rg", "head", "tail", "cat", "less", "stat", "du", "df", "basename", "dirname", "jq", "sed", "awk",
                 "tsc", "eslint", "prettier", "mkdir", "touch", "cp", "mv", "cd", "printf", "test", "[", "realpath", "find",
                 "xargs", "tr", "cut", "column", "env", "uname", "sleep", "fd", "bat", "ruff", "black", "mypy", "type",
                 "command", "export", "set", "source", ".", "read", "exit", "clear", "open"}
SAFE_SUBCOMMANDS = {
    "git": {"status", "diff", "log", "show", "branch", "add", "commit", "checkout", "switch", "fetch", "pull", "stash",
            "restore", "rev-parse", "remote", "tag", "merge", "rebase", "init", "clone", "blame", "grep", "ls-files", "config",
            "worktree", "cherry-pick", "reset", "describe", "shortlog"},
    "npm": {"test", "run", "ci", "ls", "outdated", "audit", "start", "exec", "install", "i", "view", "--version", "-v", "init"},
    "pnpm": {"test", "run", "install", "i", "ls", "build", "dev", "lint", "exec"},
    "yarn": {"test", "run", "install", "build", "dev", "lint"},
    "bun": {"test", "run", "install", "build"},
    "cargo": {"build", "test", "check", "clippy", "fmt", "run", "doc"},
    "go": {"build", "test", "vet", "fmt", "run", "mod", "version"},
    "uv": {"run", "sync", "lock", "venv", "pip", "add", "tree"},
    "make": None, "pytest": None, "vitest": None, "jest": None, "node": {"--version", "-v"},
    "python3": {"-m", "--version", "-V"}, "python": {"-m", "--version", "-V"}, "pip": {"install", "list", "show", "freeze"},
    "pip3": {"install", "list", "show", "freeze"}, "docker": {"ps", "images", "build", "compose", "logs", "version"},
    "swift": {"build", "test", "run"}, "swiftc": None, "xcodebuild": None,
    # build tools and test runners commonly behind `npm run …`
    "vite": None, "next": {"build", "dev", "start", "lint"}, "webpack": None, "rollup": None, "esbuild": None, "parcel": None,
    "turbo": {"run", "build", "test", "lint"}, "nx": {"run", "build", "test", "lint"}, "react-scripts": {"build", "test", "start"},
    "nuxt": {"build", "dev", "generate"}, "astro": {"build", "dev", "check"}, "svelte-kit": None, "ng": {"build", "test", "serve", "lint"},
    "mocha": None, "ava": None, "tap": None, "stylelint": None, "biome": None, "oxlint": None,
}
SAFE_PY_MODULES = {"pytest", "unittest", "mypy", "black", "ruff", "pip", "venv", "http.server", "json.tool", "compileall"}
SCRIPT_RUNNERS = {"python", "python3", "node", "bash", "sh", "zsh", "ruby", "perl", "deno", "bun", "ts-node", "tsx", "osascript",
                  "php", "Rscript"}
PKG_INSTALL = {"npm": {"install", "i", "add"}, "pnpm": {"add", "install", "i"}, "yarn": {"add"}, "bun": {"add", "install", "i"},
               "pip": {"install"}, "pip3": {"install"}, "uv": {"add", "pip"}, "poetry": {"add"}, "gem": {"install"},
               "cargo": {"add", "install"}, "brew": {"install"}, "npx": None, "pipx": {"install", "run"}}


def split_segments(cmd: str) -> list[list[str]]:
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    segs, cur = [], []
    try:
        for tok in lexer:
            if tok in {";", "&&", "||", "|", "&", "(", ")", "|&"}:
                if cur:
                    segs.append(cur)
                cur = []
            elif set(tok) <= set("<>&|"):
                cur.append(tok)
            else:
                cur.append(tok)
    except ValueError:
        return []
    if cur:
        segs.append(cur)
    return segs


def substitutions(cmd: str) -> list[str]:
    """Command substitutions $(...) and `...` — checked as commands of their own."""
    out = re.findall(r"\$\(([^()]*)\)", cmd) + re.findall(r"`([^`]*)`", cmd)
    return [s for s in out if s.strip()]


def program(seg: list[str]) -> tuple[str, list[str], bool]:
    i, sudo = 0, False
    while i < len(seg) and (re.match(r"^\w+=", seg[i]) or seg[i] in {"sudo", "env", "nohup", "time", "command", "exec", "doas"}):
        if seg[i] in {"sudo", "doas"}:
            sudo = True
        i += 1
    if i >= len(seg):
        return "", [], sudo
    return os.path.basename(seg[i]), seg[i + 1:], sudo


HARD_DENY_CMD = [
    (r"(curl|wget)[^|;&]*\|\s*(sudo\s+)?(ba|z|da)?sh\b", "Downloads a script from the internet and runs it immediately"),
    (r"(curl|wget)[^|;&]*\|\s*(sudo\s+)?(python3?|node|perl|ruby)\b", "Downloads code from the internet and runs it immediately"),
    (r"/dev/tcp/|\bnc\b[^|;&]*\s-e\s|\bncat\b[^|;&]*--exec|socat[^|;&]*exec:|bash\s+-i\s*>&", "Opens a remote shell (a backdoor) to another computer"),
    (r"base64\s+(-d|--decode|-D)[^|;&]*\|\s*(ba|z)?sh\b", "Runs a hidden (encoded) command"),
    (r"\bdd\b[^;&|]*\bof=/dev/(r?disk|sd|nvme)", "Overwrites a whole disk"),
    (r"\bmkfs(\.\w+)?\b|\bdiskutil\s+(erase|zero|secureErase|partitionDisk)", "Erases a disk"),
    (r"chmod\s+(-R\s+)?[0-7]?777\s+/(\s|$)", "Makes every file on the system writable by anyone"),
    (r"\bsecurity\s+(dump-keychain|find-generic-password\s[^;&|]*-w|find-internet-password[^;&|]*-w|export\b)", "Reads saved passwords from the macOS Keychain"),
    (r"crontab\b[^;]*(curl|wget|nc)\b", "Installs a scheduled task that contacts the internet"),
    (r"\bcsrutil\s+disable|spctl\s+--master-disable|\bspctl\s+--global-disable", "Turns off macOS security protections"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+(-[a-zA-Z]+\s+)*(/|/\*|~|~/|\$HOME/?|/Users/?|/System|/Applications)(\s|$)", "Deletes your whole disk or home folder"),
    (r"\bkillall\s+-9\s+senti|\blaunchctl\s+(unload|bootout|remove)[^;&|]*senti|pkill[^;&|]*senti", "Tries to switch off Senti"),
    (r"history\s+-c|rm\s+[^;&|]*\.(bash|zsh)_history", "Erases your shell history (covering tracks)"),
    (r"osascript[^;&|]*(keystroke|password|System Events)[^;&|]*(password|keystroke)", "Tries to type into other apps or phish for your password"),
]


def check_bash(cmd: str, cwd: str, project: str, depth: int = 0) -> tuple[Decision | None, dict]:
    """Returns (decision or None, facts for later layers)."""
    facts: dict = {"scripts": [], "net": False, "reads_sensitive": False, "unknown": [], "inline_code": [],
                   "packages": [], "hosts": [], "deletes": [], "writes": [], "sudo": False, "resolved": []}
    for pat, why in HARD_DENY_CMD:
        if re.search(pat, cmd):
            return Decision("block", why, "L1-rules", "hard_deny", severity="critical"), facts
    if depth < 2:
        for hidden in decode_hidden(cmd):
            d, _ = check_bash(hidden, cwd, project, depth + 1)
            if d and d.verdict == "block":
                return Decision("block", "Runs a hidden (encoded) command: " + d.reason[0].lower() + d.reason[1:], "L2-detectors",
                                "decoded", severity="critical"), facts
        for sub in substitutions(cmd):
            d, f = check_bash(sub, cwd, project, depth + 1)
            if d and d.verdict == "block":
                return d, facts
            for k in ("reads_sensitive", "net"):
                facts[k] = facts[k] or f[k]
    segs = split_segments(cmd)
    if not segs:
        return (None, facts) if cmd.strip() else (Decision("allow", "Empty command", "L1-rules", "empty"), facts)
    all_safe = True
    for seg in segs:
        prog, args, sudo = program(seg)
        if sudo:
            facts["sudo"] = True
            all_safe = False
        if not prog:
            continue
        paths = [expand(a.lstrip("@").split("=", 1)[-1], cwd) for a in args
                 if a.startswith(("/", "~", "./", "../", "$HOME", "@")) or ("/" in a and not re.match(r"^\w+://", a))
                 or re.search(r"\.env\b|id_rsa|credentials|\.pem$", a)]
        redirects = [expand(seg[i + 1], cwd) for i, t in enumerate(seg[:-1]) if t in {">", ">>"}]
        facts["writes"] += redirects
        kinds = {classify_path(p) for p in paths + redirects}
        if kinds & {"sensitive", "secret_file"}:
            facts["reads_sensitive"] = True
        if "guard" in {classify_path(p) for p in redirects}:
            return Decision("block", "Tries to change or switch off Senti's own protection", "L1-rules", "guard_path",
                            severity="critical"), facts
        if prog in DB_CLIENTS:
            hosts = []
            for i, a in enumerate(args):
                if a in {"-h", "--host", "-H"} and i + 1 < len(args):
                    hosts.append(args[i + 1])
                elif a.startswith(("--host=", "-h")) and len(a) > 2 and not a.startswith("--help"):
                    hosts.append(a.split("=", 1)[-1] if "=" in a else a[2:])
                m = re.match(r"^[a-z+]+://(?:[^@/]*@)?([^:/?]+)", a)
                if m:
                    hosts.append(m.group(1))
            facts["hosts"] += hosts
            if hosts and not all(re.fullmatch(r"localhost|127\.0\.0\.1|::1", h) for h in hosts):
                facts["net"] = True
            all_safe = False
            continue
        if prog in NET_TOOLS:
            urls = [a for a in args if re.match(r"^\w+://", a)] or [a for a in args if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", a)]
            hosts = [urlparse(u if "://" in u else "http://" + u).hostname or "" for u in urls]
            if prog in {"ssh", "scp", "rsync", "sftp"}:
                hosts += [a.split("@")[-1].split(":")[0] for a in args if "@" in a or (":" in a and not a.startswith("-"))]
            facts["hosts"] += [h for h in hosts if h]
            if hosts and all(re.fullmatch(r"localhost|127\.0\.0\.1|::1|0\.0\.0\.0", h) for h in hosts):
                continue  # talking to a local dev server
            facts["net"] = True
            all_safe = False
            if any(re.match(r"^(-d|--data(-binary|-raw|-urlencode)?|-F|--form|-T|--upload-file)$", a) or a.startswith("-d@")
                   for a in args):
                facts["uploads"] = True
            continue
        if "guard" in kinds and prog not in {"cat", "ls", "head", "grep", "stat", "tail", "less", "rg", "diff"}:
            return Decision("block", "Tries to change or switch off Senti's own protection", "L1-rules", "guard_path",
                            severity="critical"), facts
        if prog in {"rm", "rmdir", "unlink", "shred", "srm", "trash"}:
            targets = paths or [expand(a, cwd) for a in args if not a.startswith("-")]
            facts["deletes"] += targets
            for t in targets:
                personal = any(t == os.path.join(HOME, d) or (inside(t, os.path.join(HOME, d)) and not inside(t, project))
                               for d in PERSONAL_DIRS)
                if t in {"/", HOME} or personal:
                    return Decision("block", f"Deletes your personal files ({short(t)})", "L1-rules", "rm_personal",
                                    severity="critical"), facts
                if kinds & {"sensitive"}:
                    return Decision("block", f"Deletes your keys or credentials ({short(t)})", "L1-rules", "rm_sensitive",
                                    severity="critical"), facts
                if not (inside(t, project) and (os.path.basename(t) in BUILD_ARTIFACTS or "*" not in t and
                                                 os.path.basename(t).endswith((".pyc", ".log", ".tmp")))):
                    all_safe = False
            continue
        if prog in PKG_INSTALL:
            subs = PKG_INSTALL[prog]
            first = next((a for a in args if not a.startswith("-")), "")
            if subs is None or first in subs:
                rest = [a for a in args if not a.startswith("-")]
                names = rest if subs is None else rest[1:]
                if prog == "uv" and first == "pip":
                    names = rest[2:] if len(rest) > 1 and rest[1] == "install" else []
                names = [n for n in names if not n.startswith((".", "/", "-r")) and n not in {"-r", "requirements.txt"}]
                if names:
                    facts["packages"] += [(prog, n) for n in names]
                    all_safe = False
                    continue
        if prog in SCRIPT_RUNNERS:
            if prog in {"python", "python3"} and args[:1] == ["-m"] and len(args) > 1 and args[1].split(".")[0] in SAFE_PY_MODULES:
                if args[1] == "pip":
                    all_safe = False
                continue
            for flag in ("-c", "-e", "--eval", "-p"):
                if flag in args:
                    i = args.index(flag)
                    if i + 1 < len(args):
                        facts["inline_code"].append(args[i + 1])
                    all_safe = False
                    break
            else:
                script = next((a for a in args if not a.startswith("-")), None)
                if script:
                    facts["scripts"].append(expand(script, cwd))
                all_safe = False
            continue
        if seg[0].startswith(("./", "/", "~")) and prog not in SAFE_PROGRAMS and prog not in SAFE_SUBCOMMANDS:
            facts["scripts"].append(expand(seg[0], cwd))
            all_safe = False
            continue
        if prog in {"cp", "mv"} and paths:
            dest = paths[-1]
            facts["writes"].append(dest)
            if classify_path(dest) == "persistence" or not inside(dest, project) and not dest.startswith(("/tmp", "/private/tmp")):
                all_safe = False
            if prog == "mv":
                facts["deletes"] += paths[:-1]
        if prog in {"npm", "pnpm", "yarn", "bun", "make"} and depth < 2:
            resolved = resolve_task_runner(prog, args, cwd)
            for rc in resolved:
                facts["resolved"].append(rc)
                d, f = check_bash(rc, cwd, project, depth + 1)
                if d and d.verdict == "block":
                    return Decision("block", f"`{prog} {' '.join(args)}` runs `{rc[:80]}`: " + d.reason[0].lower() + d.reason[1:],
                                    "L2-detectors", "resolved_" + d.rule, severity="critical"), facts
                if d is None or d.verdict != "allow":
                    all_safe = False
                facts["scripts"] += f["scripts"]
                facts["inline_code"] += f["inline_code"]
                facts["net"] = facts["net"] or f["net"]
                facts["reads_sensitive"] = facts["reads_sensitive"] or f["reads_sensitive"]
        if prog in SAFE_PROGRAMS:
            if prog == "find" and any(a in {"-delete", "-exec", "-execdir", "-ok"} for a in args):
                all_safe = False
            if prog == "xargs" or prog == "env" and args:
                all_safe = False
            if kinds & {"sensitive", "secret_file", "persistence"} or any(
                    not inside(p, project) and p != "/dev/null" and not p.startswith(("/tmp", "/private/tmp", "/usr/", "/opt/homebrew"))
                    for p in paths + redirects):
                all_safe = False
            continue
        if prog in SAFE_SUBCOMMANDS:
            subs = SAFE_SUBCOMMANDS[prog]
            first = next((a for a in args if not a.startswith("-")), "")
            if prog == "git" and first == "push":
                all_safe = False
                if any(a in {"-f", "--force", "--force-with-lease", "--mirror", "--delete"} or a.startswith("+") for a in args):
                    facts["force_push"] = True
            elif prog == "git" and first in {"reset", "clean", "checkout"} and any(a in {"--hard", "-f", "-fd", "-fdx", "."} for a in args):
                all_safe = False
                facts["destructive_git"] = True
            elif prog == "git" and first == "config" and any("hooksPath" in a or "core.sshCommand" in a for a in args):
                all_safe = False
            elif subs is not None and first not in subs and (args[:1] and args[0] not in subs):
                all_safe = False
            elif prog == "docker" and any(a in {"--privileged", "-v", "--volume"} for a in args):
                all_safe = False
            continue
        facts["unknown"].append(prog)
        all_safe = False
    if facts["net"] and facts["reads_sensitive"]:
        return Decision("block", "Sends a secret or private file to the internet", "L1-rules", "taint_net", severity="critical"), facts
    if facts.get("force_push"):
        return Decision("ask", "Force-pushes to git, which can erase other people's work", "L1-rules", "force_push",
                        severity="warning"), facts
    if all_safe:
        return Decision("allow", "Routine development command", "L1-rules", "safe_command"), facts
    return None, facts


def resolve_task_runner(prog: str, args: list[str], cwd: str) -> list[str]:
    """`npm test` / `npm run build` / `make target` → the commands they will really run."""
    out: list[str] = []
    try:
        if prog in {"npm", "pnpm", "yarn", "bun"}:
            pj = Path(cwd) / "package.json"
            if not pj.exists():
                return out
            scripts = json.loads(pj.read_text(errors="replace")).get("scripts", {}) or {}
            rest = [a for a in args if not a.startswith("-")]
            if not rest:
                return out
            name = rest[1] if rest[0] in {"run", "run-script"} and len(rest) > 1 else rest[0]
            if name in {"install", "i", "ci"}:
                name = "postinstall"
                for hook in ("preinstall", "install", "postinstall", "prepare"):
                    if hook in scripts:
                        out.append(str(scripts[hook]))
                return out
            for n in (f"pre{name}", name, f"post{name}"):
                if n in scripts:
                    out.append(str(scripts[n]))
        elif prog == "make":
            mf = next((Path(cwd) / n for n in ("Makefile", "makefile", "GNUmakefile") if (Path(cwd) / n).exists()), None)
            if mf is None:
                return out
            text = mf.read_text(errors="replace")
            targets = [a for a in args if not a.startswith("-") and "=" not in a]
            if not targets:
                m = re.search(r"^([A-Za-z0-9_.-]+)\s*:", text, re.M)
                targets = [m.group(1)] if m else []
            for t in targets:
                m = re.search(rf"^{re.escape(t)}\s*:[^\n]*\n((?:\t[^\n]*\n?)*)", text, re.M)
                if m:
                    out += [ln.strip().lstrip("@-") for ln in m.group(1).splitlines() if ln.strip()]
    except Exception:
        pass
    return out[:20]


SAFE_DOMAINS = {"docs.python.org", "developer.mozilla.org", "github.com", "api.github.com", "raw.githubusercontent.com",
                "pypi.org", "files.pythonhosted.org", "npmjs.com", "www.npmjs.com", "registry.npmjs.org", "stackoverflow.com",
                "developer.apple.com", "react.dev", "nodejs.org", "docs.anthropic.com", "learn.microsoft.com", "go.dev",
                "pkg.go.dev", "doc.rust-lang.org", "docs.rs", "crates.io", "zod.dev", "tailwindcss.com", "fastapi.tiangolo.com",
                "vitejs.dev", "vite.dev", "typescriptlang.org", "www.typescriptlang.org", "en.wikipedia.org", "readthedocs.io",
                "docs.github.com", "platform.openai.com", "opencode.ai", "code.claude.com", "docs.docker.com"}


def host_matches(host: str, patterns) -> bool:
    host = (host or "").lower()
    for p in patterns:
        p = p.lower().strip()
        if p.startswith("*."):
            if host == p[2:] or host.endswith(p[1:]):
                return True
        elif host == p or host.endswith("." + p):
            return True
    return False


def check_action(tool: str, inp: dict, cwd: str, project: str) -> tuple[Decision | None, dict]:
    facts: dict = {"scripts": [], "paths": [], "hosts": []}
    if tool == "Bash":
        return check_bash(inp.get("command", "") or "", cwd, project)
    if tool in {"Read", "Grep", "Glob", "LS", "NotebookRead"}:
        p = expand(inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or cwd, cwd)
        facts["paths"] = [p]
        kind = classify_path(p)
        if kind == "sensitive":
            return Decision("block", f"Reads a private key or credential file ({short(p)})", "L1-rules", "read_sensitive",
                            severity="critical"), facts
        if kind == "secret_file":
            return Decision("ask", f"Reads a file with passwords or API keys ({os.path.basename(p)})", "L1-rules",
                            "read_secret_file", severity="warning"), facts
        if inside(p, project):
            if tool == "Read" and re.search(r"(?i)(config|secret|credential|token|key|passw|\.ya?ml$|\.ini$|\.toml$|\.properties$)",
                                            os.path.basename(p)):
                facts["config_like"] = True
                return None, facts  # config-like file: let the judge check it fits the task
            return Decision("allow", "Reads or searches project files", "L1-rules", "read_project"), facts
        if kind == "guard":
            return Decision("allow", "Reads a configuration file", "L1-rules", "read_guard"), facts
        facts["outside_project"] = True
        return None, facts
    if tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        p = expand(inp.get("file_path") or inp.get("notebook_path") or "", cwd)
        facts["paths"] = [p]
        kind = classify_path(p)
        content = (inp.get("content") or "") + (inp.get("new_string") or "") + (inp.get("new_source") or "")
        for e in inp.get("edits", []) or []:
            content += e.get("new_string", "")
        if kind == "guard":
            return Decision("block", "Tries to change or switch off Senti's own protection", "L1-rules", "guard_path",
                            severity="critical"), facts
        if kind == "sensitive":
            return Decision("block", f"Changes your keys or credentials ({short(p)})", "L1-rules", "write_sensitive",
                            severity="critical"), facts
        if kind == "persistence":
            return Decision("ask", f"Makes a program start automatically or changes your shell setup ({short(p)})", "L1-rules",
                            "persistence", severity="warning"), facts
        if content and p.endswith(CODE_EXT + (".json", "Makefile", ".toml", ".yml", ".yaml")) or os.path.basename(p) == "Makefile":
            d = scan_code(content)
            if d is not None:
                d.reason = d.reason.replace("The script", f"The file it is writing ({os.path.basename(p)})")
                d.rule = "write_" + d.rule
                return d, facts
        secrets = find_secrets(content)
        if secrets and kind != "secret_file":
            return Decision("ask", f"Writes what looks like a real secret ({', '.join(secrets)}) into {os.path.basename(p)}",
                            "L2-detectors", "secret_in_content", severity="warning"), facts
        if match_any(p, RUN_LATER_PATTERNS) and inside(p, project):
            facts["run_later"] = True
            return None, facts  # package.json scripts, Makefile, CI: judged, they run later
        if inside(p, project):
            return Decision("allow", "Edits a file inside the project", "L1-rules", "edit_project"), facts
        if p.startswith(("/tmp/", "/private/tmp/")):
            return Decision("allow", "Writes a temporary file", "L1-rules", "edit_tmp"), facts
        facts["outside_project"] = True
        return None, facts
    if tool in {"WebFetch", "WebSearch"}:
        if tool == "WebSearch":
            return Decision("allow", "Web search", "L1-rules", "search"), facts
        host = urlparse(inp.get("url", "")).hostname or ""
        facts["hosts"] = [host]
        if re.fullmatch(r"[\d.]+", host) and host not in {"127.0.0.1", "0.0.0.0"}:
            return Decision("ask", f"Fetches content from a raw IP address ({host})", "L1-rules", "ip_url", severity="warning"), facts
        if host_matches(host, SAFE_DOMAINS) or host in {"localhost", "127.0.0.1"}:
            return Decision("allow", "Reads documentation from a known site", "L1-rules", "safe_domain"), facts
        return None, facts
    if tool in {"TodoWrite", "Task", "Agent", "ExitPlanMode", "AskUserQuestion", "BashOutput", "KillShell", "SlashCommand",
                "Skill", "ToolSearch", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "todowrite", "todoread", "task"}:
        return Decision("allow", "Agent bookkeeping", "L1-rules", "bookkeeping"), facts
    return None, facts


CODE_EXT = (".py", ".sh", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".rb", ".pl", ".zsh", ".bash", ".php", ".go", ".rs",
            ".swift", ".applescript", ".command", ".ps1")


def read_script(path: str, limit: int = 20000) -> str | None:
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def follow_imports(path: str, text: str, depth: int = 2) -> dict[str, str]:
    """Local modules a script imports (1–2 levels), so bad code can't hide in a helper module."""
    found: dict[str, str] = {}
    base = os.path.dirname(path)

    def visit(p: str, t: str, d: int):
        if d <= 0:
            return
        names: list[str] = []
        if p.endswith(".py"):
            for m in re.finditer(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", t, re.M):
                mod = (m.group(1) or m.group(2)).lstrip(".")
                names += [os.path.join(base, *mod.split(".")) + ".py", os.path.join(base, *mod.split("."), "__init__.py")]
        elif p.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")):
            for m in re.finditer(r"(?:require\(|from\s+|import\s*\()\s*['\"](\.{1,2}/[^'\"]+)['\"]", t):
                rel = os.path.normpath(os.path.join(os.path.dirname(p), m.group(1)))
                names += [rel] + [rel + e for e in (".js", ".ts", ".mjs", ".cjs", ".tsx", "/index.js", "/index.ts")]
        elif p.endswith((".sh", ".bash", ".zsh")):
            for m in re.finditer(r"^\s*(?:source|\.)\s+([^\s;]+)", t, re.M):
                names.append(expand(m.group(1), os.path.dirname(p)))
        for n in names:
            if n in found or n == path or not os.path.isfile(n):
                continue
            s = read_script(n)
            if s is not None:
                found[n] = s
                visit(n, s, d - 1)

    visit(path, text, depth)
    return dict(list(found.items())[:8])
