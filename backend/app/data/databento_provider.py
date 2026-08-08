"""Databento CME Globex provider for MNQ 1-minute OHLCV.

Historical: continuous front-month `MNQ.c.0` (calendar), with `MNQ.FUT` parent fallback.
Live/poll: clamps `end` to dataset availability; never invents bars.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
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
        self._available_end: Optional[datetime] = None

    def _dataset_available_end(self) -> datetime:
        if self._available_end is not None:
            return self._available_end
        try:
            # Dataset condition / metadata if available
            end = self._historical.metadata.get_dataset_range(dataset=self.dataset)
            # Response shape varies by client version
            if isinstance(end, dict):
                raw = end.get("end") or end.get("end_date") or end.get("available_end")
            else:
                raw = getattr(end, "end", None) or getattr(end, "end_date", None)
            if raw is not None:
                if isinstance(raw, datetime):
                    self._available_end = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
                else:
                    self._available_end = datetime.fromisoformat(
                        str(raw).replace("Z", "+00:00")
                    )
                    if self._available_end.tzinfo is None:
                        self._available_end = self._available_end.replace(tzinfo=timezone.utc)
                    return self._available_end
        except Exception as exc:
            logger.warning("Could not read dataset range (%s); using conservative lag", exc)
        # CME historical often lags; weekend/holiday gaps common
        self._available_end = datetime.now(timezone.utc) - timedelta(hours=36)
        return self._available_end

    def _clamp_end(self, end: str) -> str:
        end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        avail = self._dataset_available_end()
        if end_dt > avail:
            logger.info("Clamping end %s → available %s", end_dt, avail)
            end_dt = avail
        return end_dt.replace(microsecond=0).isoformat()

    def _to_bars(self, data) -> list[dict[str, Any]]:
        df = data.to_df()
        bars: list[dict[str, Any]] = []
        if df is None or len(df) == 0:
            return bars
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(
                {
                    "ts": ts.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
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

    def fetch_historical(
        self, start: str, end: str, symbol: str = "MNQ"
    ) -> list[dict[str, Any]]:
        end_clamped = self._clamp_end(end)
        start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_clamped.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt <= start_dt:
            logger.warning("Empty historical window after clamp: %s → %s", start, end_clamped)
            return []

        attempts = [
            {"symbols": self.symbol if symbol == "MNQ" else symbol, "stype_in": "continuous"},
            {"symbols": "MNQ.FUT", "stype_in": "parent"},
            {"symbols": "MNQ.c.0", "stype_in": "continuous"},
        ]
        last_exc: Optional[Exception] = None
        for attempt in attempts:
            try:
                logger.info(
                    "Databento historical %s stype=%s %s → %s",
                    attempt["symbols"],
                    attempt["stype_in"],
                    start_dt.date(),
                    end_dt,
                )
                data = self._historical.timeseries.get_range(
                    dataset=self.dataset,
                    symbols=attempt["symbols"],
                    schema="ohlcv-1m",
                    start=start_dt.isoformat(),
                    end=end_clamped,
                    stype_in=attempt["stype_in"],
                )
                bars = self._to_bars(data)
                if bars:
                    # Learn true available end from last bar
                    last = datetime.fromisoformat(bars[-1]["ts"].replace("Z", "+00:00"))
                    if self._available_end is None or last > self._available_end:
                        self._available_end = last
                    return bars
            except Exception as exc:
                last_exc = exc
                logger.warning("Databento attempt failed (%s): %s", attempt, exc)
                msg = str(exc)
                if "data_end_after_available_end" in msg or "available up to" in msg:
                    # Parse available end from error if present
                    import re

                    m = re.search(r"available up to '([^']+)'", msg)
                    if m:
                        try:
                            self._available_end = datetime.fromisoformat(
                                m.group(1).replace("Z", "+00:00")
                            )
                            end_clamped = self._clamp_end(end)
                            end_dt = datetime.fromisoformat(end_clamped.replace("Z", "+00:00"))
                        except Exception:
                            pass
                continue
        if last_exc:
            raise last_exc
        return []

    def poll_new_bars(self, after_ts: Optional[str] = None) -> list[dict[str, Any]]:
        """Pull recent history and return closed bars after after_ts."""
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        avail = self._dataset_available_end()
        end = min(now, avail)
        start = end - timedelta(hours=6)
        if after_ts:
            after_dt = datetime.fromisoformat(after_ts.replace("Z", "+00:00"))
            if after_dt.tzinfo is None:
                after_dt = after_dt.replace(tzinfo=timezone.utc)
            # Small overlap to avoid gaps
            start = max(start, after_dt - timedelta(minutes=2))

        bars = self.fetch_historical(start.isoformat(), end.isoformat())
        if after_ts:
            bars = [b for b in bars if b["ts"] > after_ts]
        # Exclude incomplete current minute relative to available end
        bars = [b for b in bars if b["ts"] < end.isoformat()]
        return bars
