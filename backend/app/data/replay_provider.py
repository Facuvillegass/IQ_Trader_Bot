"""Replay 1m bars from CSV: ts,open,high,low,close,volume."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from backend.app.data.provider import MarketDataProvider


class ReplayProvider(MarketDataProvider):
    name = "replay"

    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self._bars = self._load()
        self._cursor = 0

    def _load(self) -> list[dict[str, Any]]:
        if not self.csv_path.exists():
            return []
        bars: list[dict[str, Any]] = []
        with self.csv_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                bars.append(
                    {
                        "ts": row["ts"],
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row.get("volume") or 0),
                        "symbol": "MNQ",
                        "source": "replay",
                    }
                )
        bars.sort(key=lambda b: b["ts"])
        return bars

    def fetch_historical(self, start: str, end: str, symbol: str = "MNQ") -> list[dict[str, Any]]:
        return [b for b in self._bars if start <= b["ts"] <= end]

    def poll_new_bars(self, after_ts: Optional[str] = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while self._cursor < len(self._bars):
            bar = self._bars[self._cursor]
            self._cursor += 1
            if after_ts is None or bar["ts"] > after_ts:
                out.append(bar)
                break
        return out

    def all_bars(self) -> list[dict[str, Any]]:
        return list(self._bars)
