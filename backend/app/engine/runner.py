"""Bar-driven paper trading engine with restart-safe idempotency."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from dateutil import parser as date_parser

from backend.app.config import Settings
from backend.app.db.database import Database, utc_now_iso
from backend.app.engine.accounting import AccountState, mark_to_market, performance_from_trades
from backend.app.engine.execution import PaperBroker
from backend.app.engine.session import should_exit_for_session_close
from backend.app.engine.strategy import PositionState, SignalType, evaluate_signal

logger = logging.getLogger(__name__)
trading_log = logging.getLogger("trading")


class TradingEngine:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.account = self._restore_account()
        self.broker = PaperBroker(db, settings, self.account)
        self._bar_count = self.db.get_bar_count()
        self._closes_cache: Optional[list[float]] = None
        self._ensure_experiment_meta()

    def _ensure_experiment_meta(self) -> None:
        if self.db.get_meta("experiment_started_at") is None:
            # Will be set on first live/forward activation, not on mere DB init.
            self.db.set_meta("experiment_status", "INITIALIZED")
            self.db.set_meta("trading_mode", self.settings.trading_mode)
            self.db.set_meta("sma_period", str(self.settings.sma_period))
            self.db.set_meta("band_points", str(self.settings.band_points))
            self.db.log_event("INIT", "Database initialized in PAPER mode")

    def mark_experiment_started(self) -> str:
        existing = self.db.get_meta("experiment_started_at")
        if existing:
            return existing
        started = utc_now_iso()
        self.db.set_meta("experiment_started_at", started)
        self.db.set_meta("experiment_status", "RUNNING")
        self.db.log_event("EXPERIMENT_START", f"Forward test started at {started}")
        return started

    def _restore_account(self) -> AccountState:
        snap = self.db.latest_snapshot()
        if snap:
            return AccountState(
                initial_balance=self.settings.initial_balance,
                cash_balance=float(snap["cash_balance"]),
                realized_pnl=float(snap["realized_pnl"]),
                unrealized_pnl=float(snap["unrealized_pnl"]),
                equity=float(snap["equity"]),
                peak_equity=float(snap["peak_equity"]),
                drawdown=float(snap["drawdown"]),
                max_drawdown=float(snap["max_drawdown"]),
                commissions=float(snap["commissions"]),
                slippage_cost=float(snap["slippage_cost"]),
                open_position=str(snap["open_position"]),
            )
        acct = AccountState(
            initial_balance=self.settings.initial_balance,
            cash_balance=self.settings.initial_balance,
            equity=self.settings.initial_balance,
            peak_equity=self.settings.initial_balance,
        )
        self.db.insert_snapshot(
            {
                "ts": utc_now_iso(),
                "cash_balance": acct.cash_balance,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "equity": acct.equity,
                "peak_equity": acct.peak_equity,
                "drawdown": 0.0,
                "max_drawdown": 0.0,
                "commissions": 0.0,
                "slippage_cost": 0.0,
                "open_position": "FLAT",
                "reason": "ACCOUNT_INIT",
            }
        )
        return acct

    def ingest_bars(self, bars: list[dict[str, Any]], mark_processed: bool = False) -> int:
        """Insert bars. Optionally mark processed (warmup only — no trading)."""
        n = 0
        for bar in bars:
            inserted = self.db.insert_bar(bar)
            if inserted:
                self._bar_count += 1
                n += 1
            if mark_processed:
                self.db.mark_bar_processed(bar["ts"])
        self._closes_cache = None
        return n

    def warm_bars(self, bars: list[dict[str, Any]]) -> int:
        """Load historical bars for SMA warmup WITHOUT trading or mutating the account."""
        return self.ingest_bars(bars, mark_processed=True)

    def process_bars(self, bars: list[dict[str, Any]], trade: bool = True) -> int:
        """Process many bars (backtest). Returns processed count."""
        if not trade:
            return self.warm_bars(bars)
        n = 0
        for bar in bars:
            out = self.process_bar(bar, _closes_cache=True, allow_entries=True)
            if out.get("processed"):
                n += 1
        self._closes_cache = None
        return n

    def process_bar(
        self,
        bar: dict[str, Any],
        _closes_cache: bool = False,
        allow_entries: bool = True,
    ) -> dict[str, Any]:
        """Process a closed 1-minute bar. Safe to call repeatedly (idempotent)."""
        if self.settings.trading_mode != "PAPER":
            raise RuntimeError("Live trading blocked")

        bar_ts = bar["ts"]
        result: dict[str, Any] = {
            "bar_ts": bar_ts,
            "processed": False,
            "signal": SignalType.NONE.value,
            "message": "",
        }

        # Persist bar (idempotent)
        inserted = self.db.insert_bar(bar)
        if inserted:
            self._bar_count += 1
        elif self.db.bar_processed(bar_ts):
            result["message"] = "Bar already processed — skipped"
            return result

        if self.db.bar_processed(bar_ts):
            result["message"] = "Bar already processed — skipped"
            return result

        # Claim processing lock before side effects
        if not self.db.mark_bar_processed(bar_ts):
            result["message"] = "Concurrent process claimed bar"
            return result

        if _closes_cache:
            if self._closes_cache is None:
                self._closes_cache = self.db.get_recent_closes(self.settings.sma_period)
                if self._closes_cache and abs(self._closes_cache[-1] - float(bar["close"])) > 1e-9:
                    self._closes_cache.append(float(bar["close"]))
                elif not self._closes_cache:
                    self._closes_cache = [float(bar["close"])]
            else:
                self._closes_cache.append(float(bar["close"]))
                if len(self._closes_cache) > self.settings.sma_period:
                    self._closes_cache = self._closes_cache[-self.settings.sma_period :]
            closes = self._closes_cache
        else:
            closes = self.db.get_recent_closes(self.settings.sma_period)

        pos_row = self.db.get_position()
        position = PositionState(pos_row["state"])

        decision = evaluate_signal(
            close=float(bar["close"]),
            closes=closes,
            position=position,
            sma_period=self.settings.sma_period,
            band_points=self.settings.band_points,
        )

        if decision.signal != SignalType.NONE or self._bar_count % 60 == 0:
            trading_log.info(
                "%s | Close=%.2f | SMA%s=%s | EntryThr=%s | ExitThr=%s | State=%s | Signal=%s | %s",
                bar_ts,
                decision.close,
                self.settings.sma_period,
                f"{decision.sma:.2f}" if decision.sma is not None else "n/a",
                f"{decision.entry_threshold:.2f}" if decision.entry_threshold is not None else "n/a",
                f"{decision.exit_threshold:.2f}" if decision.exit_threshold is not None else "n/a",
                decision.position_before.value,
                decision.signal.value,
                decision.reason,
            )

        signal_id = None
        # Persist actionable signals always; NONE only periodically for audit density
        if decision.signal != SignalType.NONE or self._bar_count % 60 == 0:
            signal_id = self.db.insert_signal(
                {
                    "idempotency_key": f"signal:{bar_ts}:{decision.signal.value}",
                    "bar_ts": bar_ts,
                    "signal_type": decision.signal.value,
                    "position_before": decision.position_before.value,
                    "close_price": decision.close,
                    "sma": decision.sma,
                    "entry_threshold": decision.entry_threshold,
                    "exit_threshold": decision.exit_threshold,
                    "band_points": self.settings.band_points,
                    "sma_period": self.settings.sma_period,
                    "reason": decision.reason,
                }
            )

        # Execution on next available bar conceptually: for closed-bar engine we fill
        # at signal close +/- slippage (standard bar-close simulation).
        fill_ts = self._next_fill_ts(bar_ts)

        # Session close exit takes precedence / also checked while long
        session_exit = False
        try:
            bar_dt = date_parser.isoparse(bar_ts)
        except Exception:
            bar_dt = datetime.fromisoformat(bar_ts.replace("Z", "+00:00"))

        if position == PositionState.LONG and should_exit_for_session_close(
            bar_dt,
            seconds_before=self.settings.exit_on_session_close_seconds,
            enabled=self.settings.exit_on_session_close,
        ):
            session_exit = True

        actionable = decision.signal
        exit_reason = "SMA_EXIT"
        if session_exit:
            actionable = SignalType.EXIT_LONG
            exit_reason = "SESSION_CLOSE"
            # Log explicit session signal if strategy didn't already exit
            if decision.signal != SignalType.EXIT_LONG:
                signal_id = self.db.insert_signal(
                    {
                        "idempotency_key": f"signal:{bar_ts}:SESSION_CLOSE",
                        "bar_ts": bar_ts,
                        "signal_type": SignalType.EXIT_LONG.value,
                        "position_before": position.value,
                        "close_price": decision.close,
                        "sma": decision.sma,
                        "entry_threshold": decision.entry_threshold,
                        "exit_threshold": decision.exit_threshold,
                        "band_points": self.settings.band_points,
                        "sma_period": self.settings.sma_period,
                        "reason": "Exit on session close",
                    }
                ) or signal_id

        if actionable == SignalType.ENTER_LONG and not allow_entries:
            trading_log.warning(
                "%s | ENTRY blocked (MARKET_DATA_STALE / not ready) Close=%.2f",
                bar_ts,
                float(bar["close"]),
            )
            result["message"] = "Entries blocked until market data is valid"
            result["signal"] = SignalType.NONE.value
            result["processed"] = True
            return result

        if actionable in (SignalType.ENTER_LONG, SignalType.EXIT_LONG):
            # Bars required to trade
            if self._bar_count < self.settings.bars_required_to_trade:
                result["message"] = "Bars required to trade not met"
                result["processed"] = True
                return result

            exec_result = self.broker.execute(
                signal_type=actionable,
                signal_id=signal_id,
                bar_ts=bar_ts,
                signal_price=float(bar["close"]),
                fill_ts=fill_ts,
                exit_reason=exit_reason if actionable == SignalType.EXIT_LONG else "ENTRY",
                position_before=position,
            )
            result["message"] = exec_result.message
            result["signal"] = actionable.value
        else:
            result["message"] = decision.reason
            result["signal"] = SignalType.NONE.value

        # Mark-to-market; snapshot every 15 bars (plus trade events elsewhere)
        pos = self.db.get_position()
        mark_to_market(
            self.account,
            position_state=pos["state"],
            entry_price=pos.get("entry_price"),
            current_price=float(bar["close"]),
            quantity=int(pos.get("quantity") or 0),
            point_value=self.settings.point_value,
        )
        if self._bar_count % 15 == 0 or result.get("signal") != SignalType.NONE.value:
            self.db.insert_snapshot(
                {
                    "ts": bar_ts,
                    "cash_balance": self.account.cash_balance,
                    "realized_pnl": self.account.realized_pnl,
                    "unrealized_pnl": self.account.unrealized_pnl,
                    "equity": self.account.equity,
                    "peak_equity": self.account.peak_equity,
                    "drawdown": self.account.drawdown,
                    "max_drawdown": self.account.max_drawdown,
                    "commissions": self.account.commissions,
                    "slippage_cost": self.account.slippage_cost,
                    "open_position": pos["state"],
                    "reason": "BAR",
                }
            )

        result["processed"] = True
        result["sma"] = decision.sma
        result["equity"] = self.account.equity
        return result

    @staticmethod
    def _next_fill_ts(bar_ts: str) -> str:
        try:
            dt = date_parser.isoparse(bar_ts)
        except Exception:
            dt = datetime.fromisoformat(bar_ts.replace("Z", "+00:00"))
        # Fill on next bar open (1 minute later)
        nxt = dt + timedelta(minutes=1)
        return nxt.isoformat()

    def dashboard_state(self) -> dict[str, Any]:
        pos = self.db.get_position()
        latest = self.db.get_latest_bar()
        closes = self.db.get_recent_closes(self.settings.sma_period)
        from backend.app.engine.strategy import compute_sma

        sma = compute_sma(closes, self.settings.sma_period) if closes else None
        close = float(latest["close"]) if latest else None
        entry_thr = (sma + self.settings.band_points) if sma is not None else None
        exit_thr = (sma - self.settings.band_points) if sma is not None else None

        if latest and pos["state"] == "LONG" and pos.get("entry_price") is not None:
            mark_to_market(
                self.account,
                position_state="LONG",
                entry_price=float(pos["entry_price"]),
                current_price=close,
                quantity=int(pos.get("quantity") or 1),
                point_value=self.settings.point_value,
            )

        trades = self.db.get_all_trades()
        perf = performance_from_trades(trades, self.settings.initial_balance)
        duration = None
        if pos.get("entry_time") and pos["state"] == "LONG":
            try:
                entry_dt = date_parser.isoparse(pos["entry_time"])
                duration = str(datetime.now(timezone.utc) - entry_dt.astimezone(timezone.utc))
            except Exception:
                duration = None

        return {
            "account": {
                "initial_balance": self.settings.initial_balance,
                "current_balance": self.account.cash_balance,
                "current_equity": self.account.equity,
                "total_pnl": self.account.equity - self.settings.initial_balance,
                "realized_pnl": self.account.realized_pnl,
                "unrealized_pnl": self.account.unrealized_pnl,
                "max_drawdown": self.account.max_drawdown,
                "current_drawdown": self.account.drawdown,
                "commissions": self.account.commissions,
                "slippage_cost": self.account.slippage_cost,
            },
            "strategy": {
                "sma_period": self.settings.sma_period,
                "band_points": self.settings.band_points,
                "position": pos["state"],
                "current_sma": sma,
                "current_price": close,
                "entry_threshold": entry_thr,
                "exit_threshold": exit_thr,
                "bars_loaded": self._bar_count,
                "bars_required": self.settings.bars_required_to_trade,
            },
            "performance": perf,
            "current_position": {
                "state": pos["state"],
                "entry_time": pos.get("entry_time"),
                "entry_price": pos.get("entry_price"),
                "current_price": close,
                "pnl": self.account.unrealized_pnl if pos["state"] == "LONG" else 0.0,
                "duration": duration,
            },
            "meta": {
                "trading_mode": self.settings.trading_mode,
                "data_provider": self.settings.data_provider,
                "experiment_started_at": self.db.get_meta("experiment_started_at"),
                "experiment_status": self.db.get_meta("experiment_status"),
                "tz_display": self.settings.tz_display,
            },
            "trades": trades,
            "equity_curve": [
                {
                    "ts": s["ts"],
                    "equity": s["equity"],
                    "reason": s.get("reason"),
                }
                for s in self.db.get_snapshots(limit=10000)
                if s.get("reason") in ("ENTRY", "SMA_EXIT", "SESSION_CLOSE", "ACCOUNT_INIT", "BAR")
            ],
        }
