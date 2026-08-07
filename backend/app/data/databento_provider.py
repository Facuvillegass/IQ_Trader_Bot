"""Databento CME Globex provider for MNQ 1-minute OHLCV.

Uses continuous front-month symbology when available:
  MNQ.c.0  (calendar-adjusted continuous)
Fallback: MNQ.v.0 / parent MNQ depending on Databento version.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.data.provider import MarketDataProvider

logger = logging.getLogger(__name__)


class DatabentoProvider(MarketDataProvider):
    name = "databento"

    def __init__(self, api_key: str, dataset: str = "GLBX.MDP3"):
        if not api_key:
            raise ValueError("DATABENTO_API_KEY is required for databento provider")
        try:
            import databento as db
        except ImportError as exc:
            raise ImportError(
                "databento is not installed or unsupported on this Python version. "
                "Run: pip install -r requirements-databento.txt "
                "(requires a supported Python, typically 3.10–3.13)."
            ) from exc

        self._db = db
        self.api_key = api_key
        self.dataset = dataset
        self.symbol = "MNQ.c.0"
        self._historical = db.Historical(api_key)
        self._live = None

    def fetch_historical(
        self, start: str, end: str, symbol: str = "MNQ"
    ) -> list[dict[str, Any]]:
        sym = self.symbol if symbol == "MNQ" else symbol
        logger.info("Databento historical %s %s → %s", sym, start, end)
        try:
            data = self._historical.timeseries.get_range(
                dataset=self.dataset,
                symbols=sym,
                schema="ohlcv-1m",
                start=start,
                end=end,
                stype_in="continuous",
            )
        except Exception as exc:
            logger.warning("continuous symbology failed (%s); trying parent MNQ", exc)
            data = self._historical.timeseries.get_range(
                dataset=self.dataset,
                symbols="MNQ",
                schema="ohlcv-1m",
                start=start,
                end=end,
                stype_in="parent",
            )

        df = data.to_df()
        bars: list[dict[str, Any]] = []
        if df is None or len(df) == 0:
            return bars

        # Databento prices are usually already scaled in to_df()
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(
                {
                    "ts": ts.replace(microsecond=0).isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                    "symbol": "MNQ",
                    "source": "databento",
                }
            )
        return bars

    def poll_new_bars(self, after_ts: Optional[str] = None) -> list[dict[str, Any]]:
        """Pull recent intraday history (last ~2h) and return bars after after_ts."""
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        # request a short lookback window
        from datetime import timedelta

        start = end - timedelta(hours=2)
        bars = self.fetch_historical(start.isoformat(), end.isoformat())
        if after_ts:
            bars = [b for b in bars if b["ts"] > after_ts]
        # Exclude potentially incomplete current minute
        bars = [b for b in bars if b["ts"] < end.isoformat()]
        return bars
