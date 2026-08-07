"""FastAPI + embedded 24/7 trading worker.

The worker runs in its own thread and does NOT depend on HTTP traffic.
Railway health checks hit /health (and /api/health).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import routes as api_routes
from backend.app.api.routes import _health_payload, router
from backend.app.config import ROOT_DIR, get_settings
from backend.app.db.database import Database
from backend.app.engine.worker import TradingWorker
from backend.app.runtime import RUNTIME
from backend.app.utils.iso import utc_iso
from backend.app.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

STATIC_DIR = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.logs_path)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.reports_path.mkdir(parents=True, exist_ok=True)

    if settings.trading_mode != "PAPER":
        raise RuntimeError("Refusing to start: TRADING_MODE must be PAPER")

    RUNTIME.started_at = utc_iso()
    db = Database(settings.db_path)
    RUNTIME.database_ok = db.healthcheck()
    worker = TradingWorker(db, settings)

    app.state.settings = settings
    app.state.db = db
    app.state.engine = worker.engine
    app.state.worker = worker
    app.state.provider = worker.provider

    if settings.embed_worker:
        worker.start()
        logger.info("Embedded trading worker started (HTTP-independent)")

    logger.info(
        "API ready host=%s port=%s PAPER ONLY db=%s",
        settings.api_host,
        settings.bind_port,
        settings.db_path,
    )
    yield
    worker.stop()
    logger.info("Shutdown complete")


app = FastAPI(title="MNQ Paper Trading", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/health")
def root_health(request: Request):
    return _health_payload(request)


@app.get("/status")
def root_status(request: Request):
    return api_routes.status(request)


@app.get("/account")
def root_account(request: Request):
    return api_routes.account(request)


@app.get("/position")
def root_position(request: Request):
    return api_routes.position(request)


@app.get("/trades")
def root_trades(request: Request):
    return api_routes.trades(request)


if STATIC_DIR.exists():
    assets = STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")


@app.get("/")
def spa_index():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "service": "MNQ Paper Trading",
        "dashboard": "frontend dist not built — use /health or /api/state",
        "health": "/health",
    }


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.app.main:app",
        host=settings.api_host,
        port=settings.bind_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
