from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Admin
from ..security import check_password, current_admin, hash_password, make_admin_token

router = APIRouter(prefix="/api/v1/auth")


class LoginIn(BaseModel):
    email: str
    password: str


def admin_json(a: Admin) -> dict:
    return {"id": a.id, "email": a.email, "name": a.name}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    a = db.query(Admin).filter_by(email=body.email.strip().lower()).first()
    if a is None or not check_password(body.password, a.password_hash):
        raise HTTPException(401, "wrong email or password")
    return {"token": make_admin_token(a), "admin": admin_json(a)}


@router.get("/me")
def me(a: Admin = Depends(current_admin)):
    return admin_json(a)


class PasswordIn(BaseModel):
    current: str
    new: str


@router.put("/password")
def change_password(body: PasswordIn, a: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not check_password(body.current, a.password_hash):
        raise HTTPException(400, "current password is wrong")
    if len(body.new) < 8:
        raise HTTPException(422, "use at least 8 characters")
    db.get(Admin, a.id).password_hash = hash_password(body.new)
    db.commit()
    return {"ok": True}
