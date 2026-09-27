"""Database models for the org backend."""
from __future__ import annotations

import time
import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump → every issued JWT is revoked
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug, e.g. engineering
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), default="engineering")
    agent_profiles: Mapped[dict] = mapped_column(JSON, default=dict)  # per-user override: {agent: profile_id}
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    role: Mapped[Role] = relationship()


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug, e.g. developer
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=100)  # higher wins when several apply
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # applies_to, rules, judge, approvals, features, agent_overrides
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_by: Mapped[str] = mapped_column(String(200), default="system")


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    hostname: Mapped[str] = mapped_column(String(200), default="")
    platform: Mapped[str] = mapped_column(String(200), default="")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    enrolled_at: Mapped[float] = mapped_column(Float, default=time.time)
    last_seen: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[dict] = mapped_column(JSON, default=dict)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship()


class EnrollmentCode(Base):
    __tablename__ = "enrollment_codes"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), default="engineering")
    uses_left: Mapped[int] = mapped_column(Integer, default=100)
    expires_at: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = never
    email: Mapped[str] = mapped_column(String(200), default="")  # optional: code only for this person
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    note: Mapped[str] = mapped_column(String(300), default="")


class Invite(Base):
    """A personal, one-time key an admin sends to one person to enroll one Mac. Only the SHA-256 of the key is stored."""
    __tablename__ = "invites"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    created_by: Mapped[str] = mapped_column(String(200), default="")
    expires_at: Mapped[float] = mapped_column(Float, default=0.0)
    used_at: Mapped[float] = mapped_column(Float, default=0.0)
    used_device_id: Mapped[str] = mapped_column(String(64), default="")
    used_hostname: Mapped[str] = mapped_column(String(200), default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship()


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    user_email: Mapped[str] = mapped_column(String(200), default="", index=True)
    agent: Mapped[str] = mapped_column(String(64), default="", index=True)
    event: Mapped[str] = mapped_column(String(32), default="pre_tool")
    tool: Mapped[str] = mapped_column(String(128), default="")
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    layer: Mapped[str] = mapped_column(String(64), default="")
    rule: Mapped[str] = mapped_column(String(128), default="")
    severity: Mapped[str] = mapped_column(String(16), default="info")
    reason: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[str] = mapped_column(String(64), default="")
    session: Mapped[str] = mapped_column(String(128), default="")
    task: Mapped[str] = mapped_column(Text, default="")
    cwd: Mapped[str] = mapped_column(Text, default="")
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    ms: Mapped[float] = mapped_column(Float, default=0.0)
    hash: Mapped[str] = mapped_column(String(64), default="")
    prev: Mapped[str] = mapped_column(String(64), default="")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    user_email: Mapped[str] = mapped_column(String(200), default="")
    agent: Mapped[str] = mapped_column(String(64), default="")
    tool: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    cwd: Mapped[str] = mapped_column(Text, default="")
    profile_id: Mapped[str] = mapped_column(String(64), default="")
    rule: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|denied|expired
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    decided_at: Mapped[float] = mapped_column(Float, default=0.0)
    decided_by: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class KV(Base):
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class ChangeLog(Base):
    __tablename__ = "changelog"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[float] = mapped_column(Float, default=time.time)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
