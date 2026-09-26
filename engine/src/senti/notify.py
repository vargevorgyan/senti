"""macOS notifications and the approval dialog (for agents without a native 'ask', e.g. Codex, OpenCode).

Senti has no app UI; this is the operating system's own dialog. Timeouts and errors fail closed (block).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')[:900]


def gui_available() -> bool:
    return sys.platform == "darwin" and shutil.which("osascript") is not None and not os.environ.get("SENTI_NO_GUI")


async def notify(title: str, message: str, subtitle: str = "") -> None:
    if not gui_available():
        return
    script = f'display notification "{_esc(message)}" with title "{_esc(title)}"' + (f' subtitle "{_esc(subtitle)}"' if subtitle else "")
    try:
        p = await asyncio.create_subprocess_exec("osascript", "-e", script, stdout=asyncio.subprocess.DEVNULL,
                                                 stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(p.wait(), 5)
    except Exception:
        pass


async def ask_dialog(agent: str, reason: str, detail: str, timeout: int = 120) -> tuple[str, str]:
    """Returns (verdict, how): verdict is 'allow' only if the person clicked Allow once / Always allow."""
    if not gui_available():
        return "block", "no-gui"
    text = f"{agent} wants to do something I'm not sure about.\n\n{reason}\n\n{detail}"
    script = (f'display dialog "{_esc(text)}" with title "Senti: should I let this through?" '
              f'buttons {{"Always allow", "Allow once", "Block"}} default button "Block" cancel button "Block" '
              f'with icon caution giving up after {int(timeout)}')
    try:
        p = await asyncio.create_subprocess_exec("osascript", "-e", script, stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(p.communicate(), timeout + 10)
        s = out.decode()
        if "gave up:true" in s:
            return "block", "timeout"
        if "Always allow" in s:
            return "allow", "always"
        if "Allow once" in s:
            return "allow", "once"
        return "block", "user"
    except Exception:
        return "block", "error"
