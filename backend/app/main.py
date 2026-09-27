"""Senti org backend: admin API, device API (enrollment, signed profiles, SSE push, audit, judge gateway, approvals)."""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bus import bus
from .config import settings
from .db import Base, SessionLocal, engine, migrate
from .routers import admin, auth, device, gateway
from .security import client_ip, ip_allowed
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
    async with gateway.mcp.session_manager.run():  # the MCP endpoint's session manager lives as long as the app
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


class AdminAllowlist:
    """The admin API and admin sign-in answer only callers from SENTI_ADMIN_ALLOW (default: this computer and private
    networks). Macs, bots and the join endpoint are unaffected, so employees still connect from anywhere."""
    PREFIXES = ("/api/v1/admin", "/api/v1/auth")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith(self.PREFIXES) \
                and not ip_allowed(client_ip(scope), settings.admin_allow):
            body = (b'{"detail":"The admin panel can only be opened from the company network or VPN. Ask the person who '
                    b'installed Senti to add your address to SENTI_ADMIN_ALLOW."}')
            await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


app = FastAPI(title="Senti org backend", version="0.3.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(AdminAllowlist)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(device.router)
app.include_router(gateway.router)
app.mount("/api/v1/mcp", gateway.mcp_asgi_app())  # AI agents connect here with a gateway token
