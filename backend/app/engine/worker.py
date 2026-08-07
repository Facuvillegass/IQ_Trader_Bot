"""24/7 trading worker. Independent of HTTP traffic.

Startup sequence (must complete before any trading):
1. database + schema
2. load previous state
3. acquire singleton lease
4. market data check
5. recover enough bars for SMA4750
6. reconstruct SMA
7. verify position
8. mark TRADING_ENGINE_READY
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app.config import Settings
from backend.app.data.factory import create_provider
from backend.app.db.database import Database
from backend.app.engine.lock import WorkerLease
from backend.app.engine.runner import TradingEngine
from backend.app.engine.session import is_market_open
from backend.app.engine.watchdog import MarketWatchdog
from backend.app.reports.summary import write_reports
from backend.app.runtime import RUNTIME
from backend.app.utils.iso import utc_iso

logger = logging.getLogger(__name__)


class TradingWorker:
    def __init__(self, db: Database, settings: Settings, provider=None):
        self.db = db
        self.settings = settings
        self.provider = provider or create_provider(settings)
        self.engine = TradingEngine(db, settings)
        self.lease = WorkerLease(db)
        self.watchdog = MarketWatchdog(stale_after_seconds=settings.stale_after_seconds)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_bar_ts: Optional[str] = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_forever, name="trading-worker", daemon=True
        )
        self._thread.start()
        logger.info("Trading worker thread started (HTTP-independent)")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=8)
        self.lease.release()
        RUNTIME.worker_alive = False
        RUNTIME.worker_ready = False
        RUNTIME.worker_status = "STOPPED"

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run_forever(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._run_session()
                backoff = 1.0
            except Exception as exc:
                logger.exception("Worker session crashed: %s", exc)
                RUNTIME.last_error = str(exc)
                RUNTIME.worker_ready = False
                RUNTIME.worker_status = "RECOVERING"
                RUNTIME.market_data_connected = False
                self._ready = False
                if self._stop.wait(backoff):
                    break
                backoff = min(backoff * 2, 60.0)
                logger.info("Retrying worker session in %.0fs", backoff)

    def _run_session(self) -> None:
        RUNTIME.worker_alive = True
        RUNTIME.worker_status = "STARTUP"
        self._ready = False

        # 1–2. DB already opened by caller; verify schema + load state
        if not self.db.healthcheck():
            raise RuntimeError("Database healthcheck failed")
        RUNTIME.database_ok = True
        self.engine.account = self.engine._restore_account()
        self.engine._bar_count = self.db.get_bar_count()
        self.engine._closes_cache = None
        logger.info(
            "Loaded state: bars=%s position=%s equity=%.2f",
            self.engine._bar_count,
            self.db.get_position()["state"],
            self.engine.account.equity,
        )

        # 3. Singleton lease
        if not self.lease.try_acquire():
            RUNTIME.standby = True
            RUNTIME.worker_status = "STANDBY"
            RUNTIME.lease_owner = "other"
            logger.warning("Another worker holds the lease — standby (no trading)")
            while not self._stop.is_set():
                time.sleep(10)
                if self.lease.try_acquire():
                    break
            if self._stop.is_set():
                return
        RUNTIME.standby = False
        RUNTIME.lease_owner = self.lease.owner_id

        # 4–7. Market data + SMA warmup + position verify
        self._startup_validation()

        # 8. Ready
        self._ready = True
        self.db.set_meta("trading_engine_ready", "true")
        self.db.set_meta("trading_engine_ready_at", utc_iso())
        self.db.log_event("TRADING_ENGINE_READY", "Startup validation complete")
        RUNTIME.worker_ready = True
        RUNTIME.worker_status = "READY"
        logger.info("TRADING_ENGINE_READY")

        if self.settings.forward_test_enabled:
            self.engine.mark_experiment_started()

        self._catch_up_unprocessed()

        last_report = 0.0
        while not self._stop.is_set():
            if not self.lease.heartbeat():
                raise RuntimeError("Lost singleton lease")

            try:
                self._poll_once()
                RUNTIME.market_data_connected = True
                RUNTIME.last_error = None
            except Exception as exc:
                RUNTIME.market_data_connected = False
                RUNTIME.last_error = str(exc)
                logger.warning("Market data poll failed: %s", exc)
                raise

            now = time.time()
            if now - last_report >= 60:
                try:
                    write_reports(
                        self.db,
                        self.settings.reports_path,
                        self.settings.initial_balance,
                    )
                except Exception:
                    logger.exception("Report write failed")
                last_report = now

            self._stop.wait(self.settings.engine_poll_seconds)

    def _startup_validation(self) -> None:
        RUNTIME.worker_status = "VALIDATING"
        needed = self.settings.bars_required_to_trade
        have = self.db.get_bar_count()
        latest = self.db.get_latest_bar()
        self._last_bar_ts = latest["ts"] if latest else None

        # Recover missing recent bars + SMA lookback if needed
        self._backfill(needed_total=needed)
        have = self.db.get_bar_count()
        if have < needed:
            if getattr(self.provider, "name", "") == "mock":
                logger.info("Mock warmup for SMA (%s bars needed, have %s)", needed, have)
                bars = self.provider.all_bars()
                warmup = bars[: -max(5, 1)] if len(bars) > 5 else bars
                self.engine.warm_bars(warmup)
                if warmup:
                    self._last_bar_ts = warmup[-1]["ts"]
            else:
                raise RuntimeError(
                    f"Insufficient bars for SMA({needed}); have {self.db.get_bar_count()}. "
                    "Cannot mark engine ready."
                )

        closes = self.db.get_recent_closes(self.settings.sma_period)
        from backend.app.engine.strategy import compute_sma

        sma = compute_sma(closes, self.settings.sma_period)
        if sma is None:
            raise RuntimeError("Failed to reconstruct SMA after warmup")

        pos = self.db.get_position()
        if pos["state"] not in ("FLAT", "LONG"):
            raise RuntimeError(f"Invalid position state: {pos['state']}")

        RUNTIME.last_bar_time = self._last_bar_ts or (self.db.get_latest_bar() or {}).get("ts")
        logger.info(
            "Validation OK | bars=%s sma=%.2f position=%s last_bar=%s",
            self.db.get_bar_count(),
            sma,
            pos["state"],
            RUNTIME.last_bar_time,
        )

    def _backfill(self, needed_total: int) -> None:
        """Fetch missing history without trading. Never invents bars."""
        latest = self.db.get_latest_bar()
        after = latest["ts"] if latest else None
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)

        if self.db.get_bar_count() < needed_total:
            lookback_days = max(14, int(needed_total / (23 * 60)) + 5)
            start = end - timedelta(days=lookback_days)
        elif after:
            start = datetime.fromisoformat(after.replace("Z", "+00:00")) + timedelta(minutes=1)
        else:
            start = end - timedelta(hours=6)

        if start >= end:
            return

        try:
            bars = self.provider.fetch_historical(
                utc_iso(start), utc_iso(end), symbol=self.settings.symbol
            )
        except Exception as exc:
            logger.warning("Backfill fetch failed: %s", exc)
            RUNTIME.market_data_connected = False
            return

        if not bars:
            RUNTIME.market_data_connected = after is not None
            return

        started = self.db.get_meta("experiment_started_at")
        to_warm: list[dict] = []
        to_hold: list[dict] = []
        for bar in bars:
            # Before experiment start: SMA warmup only. After start: ingest but
            # do NOT mark processed — catch-up trading happens after READY.
            if started and bar["ts"] >= started:
                to_hold.append(bar)
            else:
                to_warm.append(bar)

        if to_warm:
            self.engine.warm_bars(to_warm)
        if to_hold:
            self.engine.ingest_bars(to_hold, mark_processed=False)

        self._last_bar_ts = bars[-1]["ts"]
        RUNTIME.market_data_connected = True
        RUNTIME.last_bar_time = self._last_bar_ts
        logger.info(
            "Backfill warm=%s pending_catchup=%s last=%s",
            len(to_warm),
            len(to_hold),
            self._last_bar_ts,
        )

    def _catch_up_unprocessed(self) -> None:
        """After READY: evaluate any closed bars missed during downtime. No dummy trades."""
        started = self.db.get_meta("experiment_started_at")
        pending = self.db.get_unprocessed_bars(after_ts=started)
        if not pending:
            return
        logger.info("Catch-up processing %s unprocessed bars after restart", len(pending))
        for bar in pending:
            out = self.engine.process_bar(bar, allow_entries=not RUNTIME.entries_blocked)
            self._last_bar_ts = bar["ts"]
            RUNTIME.last_bar_time = bar["ts"]
            if out.get("signal") and out["signal"] != "NONE":
                RUNTIME.last_signal_time = bar["ts"]
                self.db.set_meta("last_signal_time", bar["ts"])
                self.db.set_meta("last_signal_type", out["signal"])
        if self._last_bar_ts:
            self.db.set_meta("last_processed_bar", self._last_bar_ts)

    def _poll_once(self) -> None:
        latest = self.db.get_latest_bar()
        after = self._last_bar_ts or (latest["ts"] if latest else None)

        try:
            new_bars = self.provider.poll_new_bars(after_ts=after)
        except Exception:
            RUNTIME.market_data_connected = False
            raise

        last_known = after or (latest["ts"] if latest else None)
        stale = self.watchdog.evaluate(last_known if not new_bars else new_bars[-1]["ts"])
        RUNTIME.market_data_stale = stale
        RUNTIME.entries_blocked = stale
        if stale:
            self.db.log_event("MARKET_DATA_STALE", "No fresh bars while market open")

        if not new_bars:
            if is_market_open(datetime.now(timezone.utc)):
                logger.info("No new bars (market open). last=%s", last_known)
            return

        allow_entries = not stale
        for bar in new_bars:
            # Reconnect must not create a trade just because we reconnected.
            # Each bar is evaluated on its own close via existing idempotent engine.
            out = self.engine.process_bar(bar, allow_entries=allow_entries)
            self._last_bar_ts = bar["ts"]
            RUNTIME.last_bar_time = bar["ts"]
            if out.get("signal") and out["signal"] != "NONE":
                RUNTIME.last_signal_time = bar["ts"]
                self.db.set_meta("last_signal_time", bar["ts"])
                self.db.set_meta("last_signal_type", out["signal"])

        self.db.set_meta("last_processed_bar", self._last_bar_ts or "")
