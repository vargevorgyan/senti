"""Admin sign-in: password, then a code from an authenticator app (required; set up on the first sign-in). The session is an
HttpOnly cookie; repeated failures lock the account and the IP for a while."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Admin, ChangeLog
from ..security import (admin_from_step_token, check_password, clear_session_cookie, client_ip, current_admin, hash_password,
                        login_guard, make_admin_token, make_step_token, make_stream_ticket, new_totp_secret, otpauth_uri,
                        qr_svg_data_uri, set_session_cookie, verify_totp)

router = APIRouter(prefix="/api/v1/auth")
# checked when the email is unknown, so a wrong email takes as long as a wrong password
_DUMMY_HASH = hash_password("senti-no-such-admin")
MIN_PASSWORD = 10


class LoginIn(BaseModel):
    email: str
    password: str


class CodeIn(BaseModel):
    token: str
    code: str


def admin_json(a: Admin) -> dict:
    return {"id": a.id, "email": a.email, "name": a.name, "two_factor": bool(a.totp_enabled)}


def _check_locks(request: Request, email: str) -> None:
    for key, limit in ((f"acct:{email}", settings.login_max_failures), (f"ip:{client_ip(request.scope)}", 4 * settings.login_max_failures)):
        wait = login_guard.locked_for(key, limit)
        if wait:
            raise HTTPException(429, f"Too many failed sign-ins. Try again in {max(1, round(wait / 60))} minutes.")


def _fail(request: Request, email: str) -> None:
    login_guard.fail(f"acct:{email}")
    login_guard.fail(f"ip:{client_ip(request.scope)}")


def _signed_in(request: Request, response: Response, db: Session, a: Admin, step: int) -> dict:
    a.totp_last_step = step
    db.add(ChangeLog(actor=a.email, action="admin.sign_in", target=client_ip(request.scope)))
    db.commit()
    login_guard.reset(f"acct:{a.email}")
    set_session_cookie(response, request, make_admin_token(a))
    return {"admin": admin_json(a)}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    """Step 1: the password. Answers which second step comes next; never a session by itself."""
    email = body.email.strip().lower()
    _check_locks(request, email)
    a = db.query(Admin).filter_by(email=email).first()
    if not check_password(body.password, a.password_hash if a else _DUMMY_HASH) or a is None:
        _fail(request, email)
        raise HTTPException(401, "wrong email or password")
    if a.totp_enabled:
        return {"step": "code", "token": make_step_token(a, "mfa")}
    if not a.totp_secret:
        a.totp_secret = new_totp_secret()
        db.commit()
    uri = otpauth_uri(a.totp_secret, a.email, f"Senti {settings.org_name}")
    return {"step": "setup", "token": make_step_token(a, "setup", minutes=10), "secret": a.totp_secret, "otpauth": uri,
            "qr": qr_svg_data_uri(uri)}


@router.post("/login/code")
def login_code(body: CodeIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Step 2: the code from the authenticator app."""
    a = admin_from_step_token(db, body.token, "mfa")
    _check_locks(request, a.email)
    step = verify_totp(a.totp_secret, body.code, a.totp_last_step or 0)
    if step is None:
        _fail(request, a.email)
        raise HTTPException(401, "That code didn't work. Use the current code from your authenticator app.")
    return _signed_in(request, response, db, a, step)


@router.post("/two-factor/setup")
def two_factor_setup(body: CodeIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """First sign-in: confirm the authenticator app with one code; from now on every sign-in needs a code."""
    a = admin_from_step_token(db, body.token, "setup")
    _check_locks(request, a.email)
    step = verify_totp(a.totp_secret, body.code, a.totp_last_step or 0)
    if step is None:
        _fail(request, a.email)
        raise HTTPException(401, "That code didn't work. Check that the app shows Senti and use its current code.")
    a.totp_enabled = True
    db.add(ChangeLog(actor=a.email, action="admin.two_factor_enabled", target=a.email))
    return _signed_in(request, response, db, a, step)


@router.get("/me")
def me(a: Admin = Depends(current_admin)):
    return admin_json(a)


class PasswordIn(BaseModel):
    current: str
    new: str


@router.put("/password")
def change_password(body: PasswordIn, request: Request, response: Response, a: Admin = Depends(current_admin),
                    db: Session = Depends(get_db)):
    if not check_password(body.current, a.password_hash):
        raise HTTPException(400, "current password is wrong")
    if len(body.new) < MIN_PASSWORD:
        raise HTTPException(422, f"use at least {MIN_PASSWORD} characters")
    row = db.get(Admin, a.id)
    row.password_hash = hash_password(body.new)
    row.token_version = (row.token_version or 0) + 1  # revoke every other session
    db.add(ChangeLog(actor=a.email, action="admin.password_changed", target=a.email))
    db.commit()
    set_session_cookie(response, request, make_admin_token(row))
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, a: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    row = db.get(Admin, a.id)
    row.token_version = (row.token_version or 0) + 1
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/stream-ticket")
def stream_ticket(a: Admin = Depends(current_admin)):
    return {"ticket": make_stream_ticket(a)}
