"""First-run data: admin, roles, the three profiles from the concept draft, a demo enrollment code."""
from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from .config import settings
from .models import KV, Admin, EnrollmentCode, Profile, Role
from .security import hash_password

AGENTS = ["claude", "codex", "opencode", "cursor", "cline", "antigravity", "zcode", "hermes", "openclaw"]

BASE_FEATURES = {"undo": True, "honeytokens": True, "injection_scan": True, "scope_contract": False, "sandbox": False}

DEVELOPER = {
    "applies_to": {"roles": ["engineering"], "agents": AGENTS},
    "rules": {
        "files": {"allow": [], "deny": ["~/.ssh/**", "~/.aws/**", "~/.gnupg/**", "**/.env*", "/data/customers/**"], "ask": []},
        "network": {"allow": ["github.com", "api.github.com", "pypi.org", "files.pythonhosted.org", "registry.npmjs.org",
                              "*.corp.internal", "docs.python.org", "developer.mozilla.org"], "deny": ["pastebin.com", "transfer.sh",
                                                                                                        "webhook.site"],
                    "ask": ["*.prod.corp.internal"],
                    "otherwise": "judge"},
        "shell": {"allow": [], "deny": ["sudo *", "rm -rf ~*"], "ask": ["git push --force*", "docker run --privileged*"],
                  "otherwise": "judge"},
        "mcp": {"allow": [], "deny": [], "otherwise": "judge"},
        "packages": "check_supply_chain",
    },
    "judge": {"mode": "local_then_corporate",
              "instructions": "Production database hosts are *.prod.corp.internal - any access needs approval.\n"
                              "Customer data lives in /data/customers - it must never leave the machine.",
              "send_to_corporate": "metadata_only"},
    "on_backend_unreachable": "strict_local",
    "approvals": {"ask_goes_to": "user"},
    "features": BASE_FEATURES,
    "agent_overrides": {},
}

PM = {
    "applies_to": {"roles": ["product"], "agents": AGENTS},
    "rules": {
        "files": {"allow": ["~/Documents/**", "~/Downloads/**", "/tmp/**"], "deny": ["~/.ssh/**", "~/.aws/**", "**/.env*",
                                                                                   "/data/customers/**"], "ask": [],
                  "write": "ask", "outside_allow": "ask"},
        "network": {"allow": ["*.atlassian.net", "*.notion.so", "docs.google.com", "*.corp.internal"], "deny": [],
                    "otherwise": "ask"},
        "shell": {"allow": ["ls*", "cat *"], "deny": ["sudo *", "rm *", "git push*"], "ask": [], "otherwise": "ask"},
        "mcp": {"allow": ["mcp__jira__*", "mcp__confluence__*"], "deny": [], "otherwise": "ask"},
        "packages": "block",
    },
    "judge": {"mode": "corporate", "instructions": "Product managers read analytics and docs. Exports with customer personal data "
                                                   "are not allowed.", "send_to_corporate": "with_redacted_content"},
    "on_backend_unreachable": "strict_local",
    "approvals": {"ask_goes_to": "user"},
    "features": BASE_FEATURES,
    "agent_overrides": {},
}

AUTONOMOUS = {
    "applies_to": {"roles": ["automation"], "agents": AGENTS},
    "rules": {
        "files": {"allow": [], "deny": ["~/.ssh/**", "~/.aws/**", "**/.env*", "~/Documents/**", "~/Desktop/**"], "ask": []},
        "network": {"allow": ["github.com", "api.github.com", "registry.npmjs.org", "pypi.org"], "deny": [], "otherwise": "block"},
        "shell": {"allow": [], "deny": ["sudo *", "rm -rf *", "git push --force*", "curl *|*sh"], "ask": ["git push*"],
                  "otherwise": "judge"},
        "mcp": {"allow": [], "deny": [], "otherwise": "ask"},
        "packages": "ask",
    },
    "judge": {"mode": "corporate", "instructions": "This agent runs unattended. Only explicitly granted tools and domains are "
                                                   "allowed; anything unusual goes to its owner.",
              "send_to_corporate": "with_redacted_content"},
    "on_backend_unreachable": "strict_local",
    "approvals": {"ask_goes_to": "owner"},
    "features": {**BASE_FEATURES, "sandbox": True},  # unattended agents must run sandboxed
    "agent_overrides": {},
}

PROFILES = [
    ("developer", "Developer", "Own projects' code, tests, packages with supply-chain checks. No production secrets.", 100, DEVELOPER),
    ("pm", "PM / Product", "Docs, trackers and analytics. No shell changes, no repo writes, no customer data exports.", 100, PM),
    ("autonomous-agent", "Autonomous agent", "Only explicitly granted tools and domains. Approvals go to the owner.", 100,
     AUTONOMOUS),
]
ROLES = [("engineering", "Engineering", "Software engineers"), ("product", "Product", "PMs and designers"),
         ("automation", "Automation", "Unattended agents and bots, each with a human owner")]


def seed(db: Session) -> None:
    if not db.query(Admin).first():
        db.add(Admin(email=settings.admin_email, name="Administrator", password_hash=hash_password(settings.admin_password)))
    for rid, name, desc in ROLES:
        if not db.get(Role, rid):
            db.add(Role(id=rid, name=name, description=desc))
    for pid, name, desc, prio, data in PROFILES:
        if not db.get(Profile, pid):
            db.add(Profile(id=pid, name=name, description=desc, priority=prio, data=copy.deepcopy(data)))
    if settings.demo_enroll_code and not db.get(EnrollmentCode, settings.demo_enroll_code):
        import time as _t
        db.add(EnrollmentCode(code=settings.demo_enroll_code, role_id="engineering", uses_left=20, expires_at=_t.time() + 7 * 86400,
                              note="demo code (SENTI_DEMO_ENROLL_CODE)"))
    if not db.get(KV, "corporate_model"):
        db.add(KV(key="corporate_model", value={"url": settings.corp_model_url, "model": settings.corp_model,
                                                "api_key": settings.corp_model_api_key, "enabled": True}))
    if not db.get(KV, "bundle_rev"):
        db.add(KV(key="bundle_rev", value={"rev": 1}))
    db.commit()
