#!/usr/bin/env python3
"""Historical sanity check for 2024 (or configured year).

Does NOT optimize parameters. Only verifies the frozen strategy engine
produces results in a plausible range vs NinjaTrader reference.

Reference 2024 (NinjaTrader):
  Net Profit ~$5,144 | PF ~1.22 | Max DD ~$3,877 | Trades ~218
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.config import Settings
from backend.app.data.factory import create_provider
from backend.app.data.mock_provider import MockProvider
from backend.app.db.database import Database
from backend.app.engine.accounting import performance_from_trades
from backend.app.engine.runner import TradingEngine
from backend.app.utils.logging_setup import setup_logging


REF_2024 = {
    "net_profit": 5144,
    "profit_factor": 1.22,
    "max_drawdown": 3877,
    "trades": 218,
}


def run_backtest_on_bars(bars: list[dict], db_path: Path, settings: Settings) -> dict:
    if db_path.exists():
        db_path.unlink()
    db = Database(db_path)
    engine = TradingEngine(db, settings)
    # Full trading backtest (this IS a historical simulation, not the forward account)
    engine.process_bars(bars, trade=True)
    # Force flatten at end for accounting completeness if still long
    pos = db.get_position()
    if pos["state"] == "LONG" and bars:
        last = bars[-1]
        from backend.app.engine.strategy import PositionState, SignalType

        engine.broker.execute(
            signal_type=SignalType.EXIT_LONG,
            signal_id=None,
            bar_ts=last["ts"],
            signal_price=float(last["close"]),
            fill_ts=last["ts"],
            exit_reason="SANITY_END",
            position_before=PositionState.LONG,
        )
    perf = performance_from_trades(db.get_all_trades(), settings.initial_balance)
    snap = db.latest_snapshot()
    return {
        "performance": perf,
        "max_drawdown": snap["max_drawdown"] if snap else None,
        "bars": len(bars),
        "equity": snap["equity"] if snap else None,
    }


def plausible(perf: dict, max_dd: float, year: int) -> tuple[bool, list[str]]:
    warnings = []
    ok = True
    if year != 2024:
        return True, ["Non-2024 year — skipping band checks"]

    trades = perf["total_trades"]
    net = perf["total_net_pnl"]
    pf = perf["profit_factor"]

    # Wide bands: feeds/contracts differ. Fail only if wildly off.
    if trades < 50 or trades > 500:
        ok = False
        warnings.append(f"Trades={trades} far from ~218")
    else:
        warnings.append(f"Trades={trades} within broad band vs ~218")

    if net < -5000 or net > 20000:
        ok = False
        warnings.append(f"Net PnL=${net:.0f} far from ~$5144")
    else:
        warnings.append(f"Net PnL=${net:.0f} within broad band vs ~$5144")

    if pf is not None and (pf < 0.5 or pf > 3.0):
        ok = False
        warnings.append(f"PF={pf:.2f} far from ~1.22")
    elif pf is not None:
        warnings.append(f"PF={pf:.2f} within broad band vs ~1.22")

    if max_dd is not None and (max_dd < 200 or max_dd > 15000):
        ok = False
        warnings.append(f"MaxDD=${max_dd:.0f} far from ~$3877")
    elif max_dd is not None:
        warnings.append(f"MaxDD=${max_dd:.0f} within broad band vs ~$3877")

    return ok, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--force-mock", action="store_true", help="Use synthetic bars")
    args = parser.parse_args()

    settings = Settings(
        trading_mode="PAPER",
        data_provider="mock" if args.force_mock else Settings().data_provider,
        database_path="data/sanity_check.db",
    )
    # Re-read env but keep paper
    env_settings = Settings()
    settings = env_settings.model_copy(
        update={
            "trading_mode": "PAPER",
            "database_path": "data/sanity_check.db",
            "data_provider": "mock" if args.force_mock else env_settings.data_provider,
        }
    )
    setup_logging(settings.logs_path)

    print("=" * 60)
    print(f"SANITY CHECK — frozen SMA{settings.sma_period} / Band{settings.band_points}")
    print(f"Year: {args.year}")
    print(f"Provider: {settings.data_provider}")
    print("=" * 60)

    bars: list[dict] = []
    mode = "mock"

    if not args.force_mock and settings.databento_api_key and settings.data_provider == "databento":
        try:
            provider = create_provider(settings)
            start = f"{args.year}-01-01"
            end = f"{args.year}-12-31"
            # Need lookback before year for SMA warm-up (~4750 minutes ≈ 3.3 trading days;
            # with ETH ~23h/day ≈ 4 calendar days; use 10 calendar days prior)
            from datetime import datetime, timedelta

            start_dt = datetime.fromisoformat(start) - timedelta(days=14)
            bars = provider.fetch_historical(start_dt.date().isoformat(), end)
            mode = "databento"
        except Exception as exc:
            print(f"Databento fetch failed: {exc}")
            print("Falling back to mock structural sanity check.")
            bars = []

    if not bars:
        # Structural sanity: generate long synthetic series and ensure engine works
        mock = MockProvider(start_price=18000.0, seed_bars=12000)
        bars = mock.all_bars()
        mode = "mock"
        print("NOTE: Using MOCK bars — this validates engine mechanics, not NT 2024 numbers.")
        print("Add DATABENTO_API_KEY and set DATA_PROVIDER=databento for real 2024 check.")

    db_path = ROOT / "data" / "sanity_check.db"
    result = run_backtest_on_bars(bars, db_path, settings)
    perf = result["performance"]
    ok, notes = plausible(perf, result["max_drawdown"], args.year if mode == "databento" else 0)

    out = {
        "mode": mode,
        "year": args.year,
        "reference_2024": REF_2024,
        "result": result,
        "plausible": ok,
        "notes": notes,
    }
    out_path = ROOT / "reports" / "sanity_check.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))

    print(json.dumps(out, indent=2, default=str))
    if mode == "mock":
        print("\nSANITY (structural): PASS" if ok else "\nSANITY (structural): FAIL")
        return 0 if ok else 1

    if not ok:
        print("\nSANITY CHECK FAILED — do NOT launch forward test until investigated.")
        return 2
    print("\nSANITY CHECK PASSED (plausible vs NinjaTrader 2024 reference).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
