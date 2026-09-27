"""Build the signed profile bundle for one device (its user's role + per-agent assignments)."""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .bus import bus
from .config import settings
from .models import KV, ChangeLog, Device, Profile
from .signing import sign

AGENTS = ["claude", "codex", "opencode", "generic"]


def bump(db: Session, actor: str, action: str, target: str = "", detail: dict | None = None) -> int:
    kv = db.get(KV, "bundle_rev")
    rev = (kv.value.get("rev", 1) if kv else 1) + 1
    if kv:
        kv.value = {"rev": rev}
    else:
        db.add(KV(key="bundle_rev", value={"rev": rev}))
    db.add(ChangeLog(actor=actor, action=action, target=target, detail=detail or {}))
    db.commit()
    bus.publish("devices", {"type": "profiles_changed", "rev": rev})
    bus.publish("admin", {"type": "change", "action": action, "target": target, "actor": actor, "ts": time.time()})
    return rev


def profile_doc(p: Profile) -> dict:
    return {"id": p.id, "name": p.name, "description": p.description, "version": p.version, "priority": p.priority, **p.data}


def resolve(db: Session, device: Device) -> dict:
    user = device.user
    role = user.role_id
    profiles = db.query(Profile).order_by(Profile.priority.desc(), Profile.id).all()
    for_role = [p for p in profiles if not (p.data.get("applies_to") or {}).get("roles") or role in p.data["applies_to"]["roles"]]
    default = for_role[0] if for_role else None  # no profile for this role → the Mac uses its strict built-in profile
    assignments: dict[str, str] = {}
    for agent in AGENTS:
        pick = next((p for p in for_role if agent in ((p.data.get("applies_to") or {}).get("agents") or [])), None)
        if pick:
            assignments[agent] = pick.id
    for agent, pid in (user.agent_profiles or {}).items():  # per-user overrides set by the admin
        if db.get(Profile, pid):
            assignments[agent] = pid
    used = {default.id} if default else set()
    used |= set(assignments.values())
    kv = db.get(KV, "bundle_rev")
    return {
        "version": kv.value.get("rev", 1) if kv else 1,
        "org": settings.org_name,
        "issued_at": time.time(),
        "device_id": device.id,
        "user": {"email": user.email, "name": user.name, "role": role},
        "default": default.id if default else None,
        "assignments": assignments,
        "profiles": [profile_doc(p) for p in profiles if p.id in used],
    }


def signed_bundle(db: Session, device: Device) -> dict:
    return sign(resolve(db, device))
