"""Senti org backend: admin API, device API (enrollment, signed profiles, SSE push, audit, judge gateway, approvals)."""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bus import bus
from .config import settings
from .db import Base, SessionLocal, engine, migrate
from .routers import admin, auth, device
from .seed import seed
from .signing import private_key


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    migrate(engine)
    with SessionLocal() as db:
        seed(db)
    private_key()  # create the signing key on first run
    bus.loop = asyncio.get_running_loop()
    warm = asyncio.create_task(_warm_corporate_model())
    yield
    warm.cancel()


async def _warm_corporate_model() -> None:
    """Load the corporate model into memory at startup so the first real verdict isn't a cold-start timeout."""
    import httpx

    from .routers.device import corp_config
    await asyncio.sleep(2)
    with SessionLocal() as db:
        cfg = corp_config(db)
    if not cfg.get("enabled", True):
        return
    for _ in range(20):
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(cfg["url"].rstrip("/") + "/chat/completions",
                                 headers={"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {},
                                 json={"model": cfg["model"], "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1})
                if r.status_code == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(15)


app = FastAPI(title="Senti org backend", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(device.router)
