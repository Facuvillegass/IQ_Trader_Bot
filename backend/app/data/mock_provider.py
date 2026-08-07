"""Synthetic MNQ 1m bars for local paper trading without credentials.

Generates sustained runs so price can diverge ±50+ points from SMA(4750),
producing real ENTER/EXIT cycles for end-to-end validation.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.app.data.provider import MarketDataProvider


class MockProvider(MarketDataProvider):
    name = "mock"

    def __init__(self, start_price: float = 20_000.0, seed_bars: int = 6000):
        self.start_price = start_price
        self.seed_bars = seed_bars
        self._cursor = 0
        self._bars: list[dict[str, Any]] = []
        self._generate_seed()

    def _drift_at(self, i: int) -> float:
        # Regime blocks ~800 bars: strong up, quiet, strong down, quiet...
        cycle = i % 1600
        if cycle < 500:
            return 0.35  # grind up ~175 pts over 500 bars → crosses +50 vs SMA
        if cycle < 800:
            return 0.02 * math.sin(i / 20.0)
        if cycle < 1300:
            return -0.35  # grind down → crosses -50 vs SMA
        return 0.02 * math.sin(i / 17.0)

    def _generate_seed(self) -> None:
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        start = end - timedelta(minutes=self.seed_bars + 200)
        price = self.start_price
        ts = start
        bars: list[dict[str, Any]] = []
        i = 0
        while ts <= end:
            drift = self._drift_at(i)
            open_p = price
            close_p = price + drift
            high_p = max(open_p, close_p) + 0.5
            low_p = min(open_p, close_p) - 0.5
            bars.append(
                {
                    "ts": ts.replace(microsecond=0).isoformat(),
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2),
                    "volume": 100 + (i % 50),
                    "symbol": "MNQ",
                    "source": "mock",
                }
            )
            price = close_p
            ts += timedelta(minutes=1)
            i += 1
        self._bars = bars
        # Leave a handful for the live poll loop
        self._cursor = max(0, len(bars) - 8)

    def fetch_historical(self, start: str, end: str, symbol: str = "MNQ") -> list[dict[str, Any]]:
        return [b for b in self._bars if start <= b["ts"] <= end]

    def poll_new_bars(self, after_ts: Optional[str] = None) -> list[dict[str, Any]]:
        if self._cursor >= len(self._bars):
            last = self._bars[-1]
            last_ts = datetime.fromisoformat(last["ts"])
            nxt = last_ts + timedelta(minutes=1)
            i = len(self._bars)
            drift = self._drift_at(i)
            open_p = float(last["close"])
            close_p = open_p + drift
            bar = {
                "ts": nxt.isoformat(),
                "open": round(open_p, 2),
                "high": round(max(open_p, close_p) + 0.25, 2),
                "low": round(min(open_p, close_p) - 0.25, 2),
                "close": round(close_p, 2),
                "volume": 120,
                "symbol": "MNQ",
                "source": "mock",
            }
            self._bars.append(bar)
        out = []
        while self._cursor < len(self._bars):
            bar = self._bars[self._cursor]
            self._cursor += 1
            if after_ts is None or bar["ts"] > after_ts:
                out.append(bar)
                break
        return out

    def all_bars(self) -> list[dict[str, Any]]:
        return list(self._bars)
