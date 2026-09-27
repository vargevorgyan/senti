"""Internal, agent-neutral event and decision types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Verdict = Literal["allow", "ask", "block"]
SEVERITY = {"allow": 0, "ask": 1, "block": 2}


@dataclass
class Action:
    """One thing an agent wants to do, normalised from any agent's hook payload.

    ``tool`` uses Claude Code's names as the canonical vocabulary:
    Bash, Read, Write, Edit, Grep, Glob, LS, WebFetch, WebSearch, mcp__<server>__<tool>, or the raw name.
    """

    agent: str
    tool: str
    input: dict[str, Any]
    cwd: str
    session_id: str = ""
    event: Literal["pre_tool", "prompt", "post_tool"] = "pre_tool"
    raw_tool: str = ""
    prompt: str = ""
    response: Any = None  # tool output for post_tool events
    identity: dict | None = None  # peer-process verification result (see identity.py)


@dataclass
class Decision:
    verdict: Verdict
    reason: str
    layer: str
    rule: str = ""
    p: dict[str, float] | None = None
    severity: Literal["info", "warning", "critical"] = "info"
    meta: dict[str, Any] = field(default_factory=dict)

    def stricter(self, other: "Decision | None") -> "Decision":
        if other is None:
            return self
        return other if SEVERITY[other.verdict] > SEVERITY[self.verdict] else self


def strictest(*ds: "Decision | None") -> "Decision | None":
    best: Decision | None = None
    for d in ds:
        if d is None:
            continue
        if best is None or SEVERITY[d.verdict] > SEVERITY[best.verdict]:
            best = d
    return best
