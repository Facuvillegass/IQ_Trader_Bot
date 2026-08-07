"""Daily and performance JSON report writers."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.db.database import Database
from backend.app.engine.accounting import performance_from_trades


def write_reports(db: Database, reports_dir: Path, initial_balance: float) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    trades = db.get_closed_trades()
    snapshots = db.get_snapshots(limit=100_000)
    perf = performance_from_trades(db.get_all_trades(), initial_balance)

    # Daily aggregation from snapshots
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in snapshots:
        day = str(s["ts"])[:10]
        by_day[day].append(s)

    closed_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in trades:
        day = str(t.get("exit_time") or "")[:10]
        if day:
            closed_by_day[day].append(t)

    daily_rows = []
    for day in sorted(by_day.keys()):
        snaps = by_day[day]
        start_eq = float(snaps[0]["equity"])
        end_eq = float(snaps[-1]["equity"])
        peak = start_eq
        max_intra_dd = 0.0
        for s in snaps:
            eq = float(s["equity"])
            peak = max(peak, eq)
            max_intra_dd = max(max_intra_dd, peak - eq)
        day_trades = closed_by_day.get(day, [])
        wins = sum(1 for t in day_trades if (t.get("net_pnl") or 0) > 0)
        losses = sum(1 for t in day_trades if (t.get("net_pnl") or 0) <= 0)
        daily_rows.append(
            {
                "date": day,
                "starting_equity": start_eq,
                "ending_equity": end_eq,
                "daily_pnl": end_eq - start_eq,
                "trades": len(day_trades),
                "wins": wins,
                "losses": losses,
                "max_intraday_dd": max_intra_dd,
                "open_position": snaps[-1]["open_position"],
            }
        )

    # Write latest day + full series
    latest_day = daily_rows[-1] if daily_rows else {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "starting_equity": initial_balance,
        "ending_equity": initial_balance,
        "daily_pnl": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "max_intraday_dd": 0.0,
        "open_position": "FLAT",
    }

    daily_path = reports_dir / "daily_summary.json"
    daily_path.write_text(json.dumps(latest_day, indent=2))
    (reports_dir / "daily_summary_history.json").write_text(
        json.dumps(daily_rows, indent=2)
    )

    perf_out = {
        **perf,
        "initial_balance": initial_balance,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "experiment_started_at": db.get_meta("experiment_started_at"),
    }
    (reports_dir / "performance_summary.json").write_text(
        json.dumps(perf_out, indent=2)
    )
    return {"daily": latest_day, "performance": perf_out}
