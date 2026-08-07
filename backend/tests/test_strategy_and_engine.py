"""Required automated tests for the frozen MNQ paper strategy."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.config import Settings
from backend.app.db.database import Database
from backend.app.engine.accounting import (
    mnq_gross_pnl,
    apply_fill_costs,
    simulate_market_fill_price,
)
from backend.app.engine.execution import PaperBroker
from backend.app.engine.runner import TradingEngine
from backend.app.engine.session import should_exit_for_session_close
from backend.app.engine.strategy import (
    PositionState,
    SignalType,
    evaluate_signal,
)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        trading_mode="PAPER",
        data_provider="mock",
        database_path=str(tmp_path / "test.db"),
        sma_period=10,  # shorter for unit tests of engine wiring; strategy unit tests use 4750 logic separately
        bars_required_to_trade=10,
        band_points=50,
        commission_per_side=0.62,
        slippage_ticks=1,
        initial_balance=10000,
    )


@pytest.fixture
def engine(settings):
    db = Database(Path(settings.database_path))
    return TradingEngine(db, settings)


def _closes(n: int, base: float = 1000.0) -> list[float]:
    return [base + i * 0.01 for i in range(n)]


def test_1_close_below_threshold_no_entry():
    closes = _closes(4750, 10000.0)
    sma = sum(closes[-4750:]) / 4750
    close = sma + 49.0  # below SMA+50
    d = evaluate_signal(
        close=close,
        closes=closes,
        position=PositionState.FLAT,
        sma_period=4750,
        band_points=50,
    )
    assert d.signal == SignalType.NONE


def test_2_close_above_threshold_while_flat_enters():
    closes = _closes(4750, 10000.0)
    sma = sum(closes[-4750:]) / 4750
    close = sma + 50.25
    d = evaluate_signal(
        close=close,
        closes=closes,
        position=PositionState.FLAT,
        sma_period=4750,
        band_points=50,
    )
    assert d.signal == SignalType.ENTER_LONG


def test_3_already_long_no_second_entry():
    closes = _closes(4750, 10000.0)
    sma = sum(closes[-4750:]) / 4750
    close = sma + 100
    d = evaluate_signal(
        close=close,
        closes=closes,
        position=PositionState.LONG,
        sma_period=4750,
        band_points=50,
    )
    assert d.signal == SignalType.NONE


def test_4_close_below_exit_while_long():
    closes = _closes(4750, 10000.0)
    sma = sum(closes[-4750:]) / 4750
    close = sma - 50.25
    d = evaluate_signal(
        close=close,
        closes=closes,
        position=PositionState.LONG,
        sma_period=4750,
        band_points=50,
    )
    assert d.signal == SignalType.EXIT_LONG


def test_5_close_below_exit_while_flat_nothing():
    closes = _closes(4750, 10000.0)
    sma = sum(closes[-4750:]) / 4750
    close = sma - 100
    d = evaluate_signal(
        close=close,
        closes=closes,
        position=PositionState.FLAT,
        sma_period=4750,
        band_points=50,
    )
    assert d.signal == SignalType.NONE


def test_6_mnq_pnl_calculation():
    # 10 points * $2 = $20
    assert mnq_gross_pnl(20000, 20010, quantity=1, point_value=2.0) == 20.0


def test_7_commission():
    c, _ = apply_fill_costs(
        commission_per_side=0.62, slippage_ticks=1, tick_value=0.5, quantity=1
    )
    assert c == 0.62


def test_8_slippage():
    buy = simulate_market_fill_price(
        signal_price=20000.0, side="BUY", tick_size=0.25, slippage_ticks=1
    )
    sell = simulate_market_fill_price(
        signal_price=20000.0, side="SELL", tick_size=0.25, slippage_ticks=1
    )
    assert buy == 20000.25
    assert sell == 19999.75
    _, slip = apply_fill_costs(
        commission_per_side=0.62, slippage_ticks=1, tick_value=0.5, quantity=1
    )
    assert slip == 0.5


def test_9_restart_does_not_duplicate_fills(engine, settings):
    base = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    # Build flat SMA then spike for entry
    price = 20000.0
    bars = []
    for i in range(15):
        ts = (base + timedelta(minutes=i)).isoformat()
        bars.append(
            {
                "ts": ts,
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": 1,
                "symbol": "MNQ",
                "source": "test",
            }
        )
    # Entry bar: close far above SMA+50
    entry_ts = (base + timedelta(minutes=15)).isoformat()
    bars.append(
        {
            "ts": entry_ts,
            "open": price,
            "high": price + 100,
            "low": price,
            "close": price + 100,
            "volume": 1,
            "symbol": "MNQ",
            "source": "test",
        }
    )
    for b in bars:
        engine.process_bar(b)

    fills_before = engine.db.connection()
    with engine.db.connection() as conn:
        n1 = conn.execute("SELECT COUNT(*) AS c FROM fills").fetchone()["c"]

    # Reprocess same bars (restart / replay)
    for b in bars:
        engine.process_bar(b)

    with engine.db.connection() as conn:
        n2 = conn.execute("SELECT COUNT(*) AS c FROM fills").fetchone()["c"]

    assert n1 == n2
    assert n1 >= 1  # at least the entry fill
    _ = fills_before


def test_10_session_close_exits_open_trade(tmp_path):
    settings = Settings(
        trading_mode="PAPER",
        data_provider="mock",
        database_path=str(tmp_path / "sess.db"),
        sma_period=5,
        bars_required_to_trade=5,
        band_points=50,
        exit_on_session_close=True,
        exit_on_session_close_seconds=30,
    )
    engine = TradingEngine(Database(Path(settings.database_path)), settings)

    # Use CT afternoon: 15:59 CT on a weekday
    # 15:59 CT = 20:59 UTC during CDT (UTC-5) in August
    base = datetime(2026, 8, 10, 20, 50, tzinfo=timezone.utc)
    price = 20000.0
    for i in range(6):
        ts = (base + timedelta(minutes=i)).isoformat()
        close = price + (80 if i == 5 else 0)  # enter on last warmup
        engine.process_bar(
            {
                "ts": ts,
                "open": price,
                "high": close + 1,
                "low": price - 1,
                "close": close,
                "volume": 1,
                "symbol": "MNQ",
                "source": "test",
            }
        )

    # Ensure long
    if engine.db.get_position()["state"] != "LONG":
        # Force long via broker for session-close focus
        from backend.app.engine.strategy import SignalType, PositionState

        engine.broker.execute(
            signal_type=SignalType.ENTER_LONG,
            signal_id=None,
            bar_ts=(base + timedelta(minutes=6)).isoformat(),
            signal_price=20100,
            fill_ts=(base + timedelta(minutes=6)).isoformat(),
            exit_reason="ENTRY",
            position_before=PositionState.FLAT,
        )

    assert engine.db.get_position()["state"] == "LONG"

    # 15:59 CT bar on Aug 10 2026 (CDT = UTC-5) => 20:59 UTC
    session_bar_ts = datetime(2026, 8, 10, 20, 59, tzinfo=timezone.utc)
    assert should_exit_for_session_close(session_bar_ts, seconds_before=30, enabled=True)

    engine.process_bar(
        {
            "ts": session_bar_ts.isoformat(),
            "open": 20050,
            "high": 20060,
            "low": 20040,
            "close": 20055,
            "volume": 1,
            "symbol": "MNQ",
            "source": "test",
        }
    )
    assert engine.db.get_position()["state"] == "FLAT"
    trades = engine.db.get_closed_trades()
    assert any(t.get("exit_reason") == "SESSION_CLOSE" for t in trades)


def test_live_mode_blocked():
    with pytest.raises(Exception):
        Settings(trading_mode="LIVE")


def test_stale_data_blocks_new_entries_not_exits(engine, settings):
    base = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    price = 20000.0
    for i in range(12):
        engine.process_bar(
            {
                "ts": (base + timedelta(minutes=i)).isoformat(),
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": 1,
                "symbol": "MNQ",
                "source": "test",
            }
        )
    entry_ts = (base + timedelta(minutes=12)).isoformat()
    blocked = engine.process_bar(
        {
            "ts": entry_ts,
            "open": price,
            "high": price + 100,
            "low": price,
            "close": price + 100,
            "volume": 1,
            "symbol": "MNQ",
            "source": "test",
        },
        allow_entries=False,
    )
    assert engine.db.get_position()["state"] == "FLAT"
    assert blocked["signal"] == "NONE"

    # After recovery, same-style spike on a new bar may enter
    engine.process_bar(
        {
            "ts": (base + timedelta(minutes=13)).isoformat(),
            "open": price,
            "high": price + 100,
            "low": price,
            "close": price + 100,
            "volume": 1,
            "symbol": "MNQ",
            "source": "test",
        },
        allow_entries=True,
    )
    assert engine.db.get_position()["state"] == "LONG"


def test_singleton_lease_blocks_second_worker(tmp_path):
    from backend.app.engine.lock import WorkerLease

    settings = Settings(
        trading_mode="PAPER",
        database_path=str(tmp_path / "lease.db"),
    )
    db = Database(Path(settings.database_path))
    a = WorkerLease(db, ttl_seconds=30)
    b = WorkerLease(db, ttl_seconds=30)
    assert a.try_acquire() is True
    assert b.try_acquire() is False
    a.release()
    assert b.try_acquire() is True


def test_watchdog_stale_when_market_open_without_bars():
    from backend.app.engine.watchdog import MarketWatchdog

    wd = MarketWatchdog(stale_after_seconds=60)
    # Monday 18:00 CT = Tuesday 00:00 UTC during CDT? Aug 10 2026 is Monday.
    # 18:00 CT CDT = 23:00 UTC.
    now = datetime(2026, 8, 10, 23, 0, tzinfo=timezone.utc)
    assert wd.evaluate(None, now=now) is True
    assert wd.last_event == "MARKET_DATA_STALE"
    fresh = datetime(2026, 8, 10, 22, 59, tzinfo=timezone.utc).isoformat()
    assert wd.evaluate(fresh, now=now) is False


def test_timestamps_are_utc_iso():
    from backend.app.utils.iso import ar_display, utc_iso

    ts = "2026-08-07T23:30:00+00:00"
    assert utc_iso(ts).endswith("+00:00") or utc_iso(ts).startswith("2026-08-07T23:30:00")
    assert "ART" in ar_display(ts)
    # Argentina UTC-3 in August
    assert ar_display(ts).startswith("2026-08-07 20:30:00")
