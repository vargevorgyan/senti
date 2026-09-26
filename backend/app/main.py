"""Senti org backend: admin API, device API (enrollment, signed profiles, SSE push, audit, judge gateway, approvals)."""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bus import bus
from .config import settings
from .db import Base, SessionLocal, engine
from .routers import admin, auth, device
from .seed import seed
from .signing import private_key


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    private_key()  # create the signing key on first run
    bus.loop = asyncio.get_running_loop()
    yield


app = FastAPI(title="Senti org backend", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(device.router)
