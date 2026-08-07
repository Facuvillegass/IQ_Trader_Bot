"""SQLite persistence helpers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from backend.app.db.schema import SCHEMA_SQL


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
            row = conn.execute(
                "SELECT state FROM positions WHERE id = 1"
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO positions (id, state, quantity, updated_at)
                    VALUES (1, 'FLAT', 0, ?)
                    """,
                    (utc_now_iso(),),
                )

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO meta(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, utc_now_iso()),
            )

    def insert_bar(self, bar: dict[str, Any]) -> bool:
        """Insert bar. Returns False if duplicate ts (idempotent)."""
        with self.connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO bars(ts, open, high, low, close, volume, symbol, source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bar["ts"],
                        bar["open"],
                        bar["high"],
                        bar["low"],
                        bar["close"],
                        bar.get("volume", 0),
                        bar.get("symbol", "MNQ"),
                        bar.get("source", "unknown"),
                        utc_now_iso(),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def bar_processed(self, bar_ts: str) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_bars WHERE bar_ts = ?", (bar_ts,)
            ).fetchone()
            return row is not None

    def mark_bar_processed(self, bar_ts: str) -> bool:
        with self.connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO processed_bars(bar_ts, processed_at) VALUES (?, ?)",
                    (bar_ts, utc_now_iso()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def get_recent_closes(self, limit: int) -> list[float]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT close FROM bars ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [float(r["close"]) for r in reversed(rows)]

    def get_bar_count(self) -> int:
        with self.connection() as conn:
            return int(conn.execute("SELECT COUNT(*) AS c FROM bars").fetchone()["c"])

    def get_latest_bar(self) -> Optional[dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM bars ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_bars_between(self, start_ts: str, end_ts: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM bars WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
                (start_ts, end_ts),
            ).fetchall()
            return [dict(r) for r in rows]

    def insert_signal(self, payload: dict[str, Any]) -> Optional[int]:
        with self.connection() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO signals(
                        idempotency_key, bar_ts, signal_type, position_before,
                        close_price, sma, entry_threshold, exit_threshold,
                        band_points, sma_period, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["idempotency_key"],
                        payload["bar_ts"],
                        payload["signal_type"],
                        payload["position_before"],
                        payload["close_price"],
                        payload.get("sma"),
                        payload.get("entry_threshold"),
                        payload.get("exit_threshold"),
                        payload["band_points"],
                        payload["sma_period"],
                        payload.get("reason"),
                        utc_now_iso(),
                    ),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def insert_order(self, payload: dict[str, Any]) -> Optional[int]:
        with self.connection() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO orders(
                        idempotency_key, signal_id, side, order_type, quantity,
                        signal_price, status, tif, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["idempotency_key"],
                        payload.get("signal_id"),
                        payload["side"],
                        payload.get("order_type", "MARKET"),
                        payload["quantity"],
                        payload["signal_price"],
                        payload["status"],
                        payload.get("tif", "GTC"),
                        utc_now_iso(),
                    ),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def insert_fill(self, payload: dict[str, Any]) -> Optional[int]:
        with self.connection() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO fills(
                        idempotency_key, order_id, fill_ts, fill_price, signal_price,
                        quantity, side, slippage_ticks, slippage_cost, commission,
                        commission_normalized, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["idempotency_key"],
                        payload["order_id"],
                        payload["fill_ts"],
                        payload["fill_price"],
                        payload["signal_price"],
                        payload["quantity"],
                        payload["side"],
                        payload["slippage_ticks"],
                        payload["slippage_cost"],
                        payload["commission"],
                        payload["commission_normalized"],
                        utc_now_iso(),
                    ),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def open_trade(self, payload: dict[str, Any]) -> int:
        now = utc_now_iso()
        with self.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO trades(
                    entry_signal_time, entry_time, entry_signal_price, entry_fill_price,
                    quantity, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (
                    payload.get("entry_signal_time"),
                    payload["entry_time"],
                    payload.get("entry_signal_price"),
                    payload["entry_fill_price"],
                    payload["quantity"],
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def close_trade(self, trade_id: int, payload: dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE trades SET
                    exit_signal_time = ?,
                    exit_time = ?,
                    exit_signal_price = ?,
                    exit_fill_price = ?,
                    gross_pnl = ?,
                    commission = ?,
                    commission_normalized = ?,
                    slippage_cost = ?,
                    net_pnl = ?,
                    net_pnl_normalized = ?,
                    balance_after = ?,
                    equity_after = ?,
                    exit_reason = ?,
                    status = 'CLOSED',
                    updated_at = ?
                WHERE trade_id = ?
                """,
                (
                    payload.get("exit_signal_time"),
                    payload["exit_time"],
                    payload.get("exit_signal_price"),
                    payload["exit_fill_price"],
                    payload["gross_pnl"],
                    payload["commission"],
                    payload["commission_normalized"],
                    payload["slippage_cost"],
                    payload["net_pnl"],
                    payload["net_pnl_normalized"],
                    payload["balance_after"],
                    payload["equity_after"],
                    payload["exit_reason"],
                    utc_now_iso(),
                    trade_id,
                ),
            )

    def get_open_trade(self) -> Optional[dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY trade_id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_all_trades(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY trade_id ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_closed_trades(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY trade_id ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_position(self) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM positions WHERE id = 1").fetchone()
            return dict(row)

    def set_position(self, payload: dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE positions SET
                    state = ?,
                    quantity = ?,
                    entry_time = ?,
                    entry_price = ?,
                    entry_signal_time = ?,
                    entry_signal_price = ?,
                    open_trade_id = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    payload["state"],
                    payload.get("quantity", 0),
                    payload.get("entry_time"),
                    payload.get("entry_price"),
                    payload.get("entry_signal_time"),
                    payload.get("entry_signal_price"),
                    payload.get("open_trade_id"),
                    utc_now_iso(),
                ),
            )

    def insert_snapshot(self, payload: dict[str, Any]) -> None:
        with self.connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO account_snapshots(
                        ts, cash_balance, realized_pnl, unrealized_pnl, equity,
                        peak_equity, drawdown, max_drawdown, commissions,
                        slippage_cost, open_position, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["ts"],
                        payload["cash_balance"],
                        payload["realized_pnl"],
                        payload["unrealized_pnl"],
                        payload["equity"],
                        payload["peak_equity"],
                        payload["drawdown"],
                        payload["max_drawdown"],
                        payload["commissions"],
                        payload["slippage_cost"],
                        payload["open_position"],
                        payload.get("reason"),
                    ),
                )
            except sqlite3.IntegrityError:
                pass

    def get_snapshots(self, limit: int = 5000) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM account_snapshots
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def latest_snapshot(self) -> Optional[dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM account_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def log_event(self, event_type: str, message: str, payload: Any = None) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO system_events(ts, event_type, message, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    utc_now_iso(),
                    event_type,
                    message,
                    json.dumps(payload) if payload is not None else None,
                    utc_now_iso(),
                ),
            )

    def healthcheck(self) -> bool:
        try:
            with self.connection() as conn:
                conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
                conn.execute("SELECT 1 FROM positions WHERE id = 1")
                conn.execute("SELECT 1 FROM meta LIMIT 1")
            return True
        except Exception:
            return False

    def last_processed_bar_ts(self) -> Optional[str]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT bar_ts FROM processed_bars ORDER BY bar_ts DESC LIMIT 1"
            ).fetchone()
            return row["bar_ts"] if row else None

    def get_unprocessed_bars(self, after_ts: Optional[str] = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if after_ts:
                rows = conn.execute(
                    """
                    SELECT b.* FROM bars b
                    LEFT JOIN processed_bars p ON p.bar_ts = b.ts
                    WHERE p.bar_ts IS NULL AND b.ts >= ?
                    ORDER BY b.ts ASC
                    """,
                    (after_ts,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT b.* FROM bars b
                    LEFT JOIN processed_bars p ON p.bar_ts = b.ts
                    WHERE p.bar_ts IS NULL
                    ORDER BY b.ts ASC
                    """
                ).fetchall()
            return [dict(r) for r in rows]

    def last_signal_row(self) -> Optional[dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM signals
                WHERE signal_type != 'NONE'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            return dict(row) if row else None
