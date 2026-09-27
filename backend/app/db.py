from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite:///"):
        os.makedirs(os.path.dirname(url.removeprefix("sqlite:///")) or ".", exist_ok=True)
    eng = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return eng


engine = make_engine(settings.db_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate(eng) -> None:
    """Tiny additive migrations for existing SQLite databases (create_all never alters tables)."""
    from sqlalchemy import inspect, text
    insp = inspect(eng)
    wanted = {"admins": {"token_version": "INTEGER DEFAULT 0", "totp_secret": "VARCHAR(64) DEFAULT ''",
                         "totp_enabled": "BOOLEAN DEFAULT 0", "totp_last_step": "INTEGER DEFAULT 0"},
              "enrollment_codes": {"email": "VARCHAR(200) DEFAULT ''"},
              "users": {"gateway_role": "VARCHAR(64) DEFAULT ''"},
              "devices": {"public_key": "TEXT DEFAULT ''", "key_type": "VARCHAR(32) DEFAULT ''"}}
    with eng.begin() as conn:
        for table, cols in wanted.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
