"""FastAPI application.

Run: uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs

Set COMPLIANCE_JWT_SECRET and COMPLIANCE_SECRET_KEY in production. If they are
unset the app generates them per process, which invalidates sessions and
encrypted credentials on restart -- acceptable for local development only.
"""

from __future__ import annotations

import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import init_db
from .routers import agent, auth, clients, monitoring, trust, workspace


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables and warn about missing production secrets at startup.

    Using the lifespan context (rather than @app.on_event) means the schema is
    created both under uvicorn and under TestClient, so tests exercise the same
    startup path as production.
    """
    # Prefer Alembic when it is configured, so a deployed instance is upgraded by
    # the same ordered migrations a developer ran locally. Fall back to
    # create_all() only when migrations are absent, which keeps a bare checkout
    # runnable without an init step.
    _apply_schema()
    if not os.environ.get("COMPLIANCE_JWT_SECRET"):
        print("WARNING: COMPLIANCE_JWT_SECRET is not set. Sessions will not survive a restart.")
    if not os.environ.get("COMPLIANCE_SECRET_KEY"):
        print("WARNING: COMPLIANCE_SECRET_KEY is not set. Integration credentials use a derived key.")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Compliance OS API",
    version="3.0.0",
    description=(
        "Compliance evidence automation with a Moroccan regulatory layer. "
        "This API exposes readiness assessment, continuous monitoring, and "
        "evidence management. It does not issue certifications or attestations."
    ),
)

# CORS: explicit origins only. Never wildcard with credentials.
_origins = os.environ.get("COMPLIANCE_CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-TOTP-Required"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; frame-ancestors 'none'" if request.url.path.startswith("/api") else "default-src 'self'",
    )
    return response


app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(monitoring.router)
app.include_router(trust.router)
app.include_router(workspace.router)
app.include_router(agent.router)




def _apply_schema() -> None:
    """Run Alembic migrations if configured; otherwise create tables directly."""
    here = os.path.dirname(os.path.abspath(__file__))
    backend_root = os.path.dirname(here)
    ini = os.path.join(backend_root, "alembic.ini")

    if os.path.isfile(ini):
        try:
            from alembic import command
            from alembic.config import Config

            cfg = Config(ini)
            cfg.set_main_option("script_location", os.path.join(backend_root, "migrations"))
            command.upgrade(cfg, "head")
            return
        except Exception as exc:  # noqa: BLE001 - never crash on schema setup
            print("WARNING: alembic upgrade failed (%s); falling back to create_all" % type(exc).__name__)
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "3.0.0"}
