"""Delayed continuous futures via yfinance (MNQ=F).

Limitations:
- 1m history is short (typically ~7 days)
- Delayed / not exchange-grade
Useful only as a temporary bridge until Databento is configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.data.provider import MarketDataProvider

logger = logging.getLogger(__name__)


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def __init__(self, ticker: str = "MNQ=F"):
        self.ticker = ticker

    def fetch_historical(
        self, start: str, end: str, symbol: str = "MNQ"
    ) -> list[dict[str, Any]]:
        import yfinance as yf

        t = yf.Ticker(self.ticker)
        # yfinance 1m max lookback is limited; use period for short windows
        df = t.history(interval="1m", start=start[:10], end=end[:10])
        bars: list[dict[str, Any]] = []
        if df is None or df.empty:
            logger.warning("yfinance returned no data for %s", self.ticker)
            return bars
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            iso = ts.astimezone(timezone.utc).replace(microsecond=0).isoformat()
            if start <= iso <= end:
                bars.append(
                    {
                        "ts": iso,
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0) or 0),
                        "symbol": "MNQ",
                        "source": "yfinance",
                    }
                )
        return bars

    def poll_new_bars(self, after_ts: Optional[str] = None) -> list[dict[str, Any]]:
        import yfinance as yf

        t = yf.Ticker(self.ticker)
        df = t.history(period="1d", interval="1m")
        bars: list[dict[str, Any]] = []
        if df is None or df.empty:
            return bars
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            iso = ts.astimezone(timezone.utc).replace(microsecond=0).isoformat()
            if iso >= now.isoformat():
                continue
            if after_ts and iso <= after_ts:
                continue
            bars.append(
                {
                    "ts": iso,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row.get("Volume", 0) or 0),
                    "symbol": "MNQ",
                    "source": "yfinance",
                }
            )
        return bars
