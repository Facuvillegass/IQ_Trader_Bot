"""Market data provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator, Optional


class MarketDataProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_historical(
        self,
        start: str,
        end: str,
        symbol: str = "MNQ",
    ) -> list[dict[str, Any]]:
        """Return list of 1m OHLCV bars with keys: ts, open, high, low, close, volume."""

    @abstractmethod
    def poll_new_bars(self, after_ts: Optional[str] = None) -> list[dict[str, Any]]:
        """Return newly closed 1m bars since after_ts (exclusive)."""

    def stream_live(self) -> Iterator[dict[str, Any]]:
        raise NotImplementedError("Live stream not implemented for this provider")
