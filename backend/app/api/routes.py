"""REST API for dashboard + Railway health checks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from backend.app.runtime import RUNTIME
from backend.app.utils.iso import ar_display, utc_iso

router = APIRouter()


def _engine(request: Request):
    return request.app.state.engine


def _worker(request: Request):
    return getattr(request.app.state, "worker", None)


def _health_payload(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    engine = _engine(request)
    worker = _worker(request)
    db = engine.db
    pos = db.get_position()
    latest = db.get_latest_bar()
    last_signal = db.last_signal_row()
    last_bar = RUNTIME.last_bar_time or (latest["ts"] if latest else None)
    last_sig = RUNTIME.last_signal_time or (last_signal["bar_ts"] if last_signal else None)
    db_ok = db.healthcheck()
    worker_alive = bool(worker and worker.is_alive()) if worker else RUNTIME.worker_alive
    worker_ready = bool(worker and worker.ready) if worker else RUNTIME.worker_ready
    connected = RUNTIME.market_data_connected and not RUNTIME.market_data_stale

    if not db_ok:
        status = "unhealthy"
    elif RUNTIME.standby:
        status = "standby"
    elif RUNTIME.market_data_stale:
        status = "degraded"
    elif not worker_ready:
        status = "starting"
    elif worker_alive and db_ok:
        status = "healthy"
    else:
        status = "degraded"

    return {
        "status": status,
        "worker_alive": worker_alive,
        "worker_ready": worker_ready,
        "worker_status": RUNTIME.worker_status,
        "market_data_connected": connected,
        "market_data_stale": RUNTIME.market_data_stale,
        "last_bar_time": last_bar,
        "last_bar_time_ar": ar_display(last_bar) if last_bar else None,
        "last_signal_time": last_sig,
        "last_signal_time_ar": ar_display(last_sig) if last_sig else None,
        "position": pos["state"],
        "equity": round(float(engine.account.equity), 2),
        "uptime": round(RUNTIME.uptime_seconds(), 1),
        "uptime_seconds": round(RUNTIME.uptime_seconds(), 1),
        "database_ok": db_ok,
        "trading_mode": settings.trading_mode,
        "data_provider": settings.data_provider,
        "paper_only": True,
        "standby": RUNTIME.standby,
        "entries_blocked": RUNTIME.entries_blocked,
        "last_error": RUNTIME.last_error,
        "tz_internal": "UTC",
        "tz_display": settings.tz_display,
        "now_utc": utc_iso(),
        "now_ar": ar_display(datetime.now(timezone.utc)),
    }


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    return _health_payload(request)


@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    payload = _health_payload(request)
    db = _engine(request).db
    payload.update(
        {
            "experiment_started_at": db.get_meta("experiment_started_at"),
            "experiment_status": db.get_meta("experiment_status"),
            "trading_engine_ready": db.get_meta("trading_engine_ready"),
            "bars_loaded": _engine(request)._bar_count,
            "lease_owner": RUNTIME.lease_owner,
        }
    )
    return payload


@router.get("/account")
def account(request: Request) -> dict[str, Any]:
    return _engine(request).dashboard_state()["account"]


@router.get("/position")
def position(request: Request) -> dict[str, Any]:
    return _engine(request).dashboard_state()["current_position"]


@router.get("/trades")
def trades(request: Request) -> list[dict[str, Any]]:
    return _engine(request).db.get_all_trades()


@router.get("/state")
def state(request: Request) -> dict[str, Any]:
    data = _engine(request).dashboard_state()
    data["health"] = _health_payload(request)
    return data


@router.get("/equity")
def equity(request: Request) -> list[dict[str, Any]]:
    snaps = _engine(request).db.get_snapshots(limit=20000)
    out = []
    for i, s in enumerate(snaps):
        reason = s.get("reason")
        if reason in ("ENTRY", "SMA_EXIT", "SESSION_CLOSE", "ACCOUNT_INIT") or i % 15 == 0:
            out.append(
                {
                    "ts": s["ts"],
                    "ts_ar": ar_display(s["ts"]),
                    "equity": s["equity"],
                    "reason": reason,
                    "open_position": s["open_position"],
                }
            )
    return out


@router.post("/engine/start")
def start_experiment(request: Request) -> dict[str, Any]:
    started = _engine(request).mark_experiment_started()
    return {"experiment_started_at": started, "status": "RUNNING"}


@router.get("/meta")
def meta(request: Request) -> dict[str, Any]:
    db = _engine(request).db
    settings = request.app.state.settings
    return {
        "experiment_started_at": db.get_meta("experiment_started_at"),
        "experiment_status": db.get_meta("experiment_status"),
        "trading_mode": db.get_meta("trading_mode"),
        "sma_period": db.get_meta("sma_period"),
        "band_points": db.get_meta("band_points"),
        "tz_display": settings.tz_display,
    }
