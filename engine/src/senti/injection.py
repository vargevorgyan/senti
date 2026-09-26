"""Post-read prompt-injection scanning: warn the agent when content it just read tries to instruct it."""
from __future__ import annotations

import re

PATTERNS = [
    (r"(?i)ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules)", "tells the agent to ignore its instructions"),
    (r"(?i)(ai|llm|coding)\s+(agents?|assistants?|models?)\s*[:,]?\s*(please\s+)?(must|should|need to|before|run|execute|always|first)", "contains orders addressed to AI agents"),
    (r"(?i)<!--[^>]{0,400}(curl|wget|run|execute|agent|assistant)[^>]{0,400}-->", "hides commands in an HTML comment"),
    (r"(?i)(curl|wget|nc)\b[^\n]{0,120}(@\.env|@~/\.ssh|id_rsa|\.aws/credentials|-d\s*@)", "asks to send secret files somewhere"),
    (r"(?i)(do not|don't|never)\s+(tell|inform|mention to|show)\s+(the\s+)?(user|human)", "tells the agent to hide things from you"),
    (r"(?i)you\s+are\s+now\s+(in\s+)?(developer|dan|jailbreak|god)\s*mode", "tries to jailbreak the agent"),
    (r"(?i)(system|admin)\s*(prompt|override|message)\s*:", "pretends to be a system message"),
    (r"[​‌‍⁠﻿]{3,}|[\U000E0000-\U000E007F]{3,}", "contains invisible characters that can hide instructions"),
]


def scan(text: str) -> list[str]:
    if not text:
        return []
    text = text[:200_000]
    return [why for pat, why in PATTERNS if re.search(pat, text)]


def response_text(resp) -> str:
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        parts = []
        for k in ("content", "output", "stdout", "stderr", "text", "result", "file", "body"):
            v = resp.get(k)
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, dict):
                parts.append(response_text(v))
            elif isinstance(v, list):
                parts += [response_text(x) for x in v]
        return "\n".join(parts) if parts else str(resp)
    if isinstance(resp, list):
        return "\n".join(response_text(x) for x in resp)
    return str(resp)
