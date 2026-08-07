"""Market-data watchdog. Never invents bars. Blocks entries when stale."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.app.engine.session import is_market_open
from backend.app.utils.iso import parse_utc

logger = logging.getLogger(__name__)


class MarketWatchdog:
    def __init__(self, stale_after_seconds: int = 180):
        self.stale_after_seconds = stale_after_seconds
        self.stale = False
        self.last_event: Optional[str] = None

    def evaluate(self, last_bar_ts: Optional[str], now: Optional[datetime] = None) -> bool:
        """Return True if market data is considered stale. Side-effect: updates self.stale."""
        now = now or datetime.now(timezone.utc)
        if not is_market_open(now):
            if self.stale:
                logger.info("Market closed — clearing MARKET_DATA_STALE flag")
            self.stale = False
            self.last_event = None
            return False

        if not last_bar_ts:
            self._mark_stale("No bars received while market is open")
            return True

        age = (now - parse_utc(last_bar_ts)).total_seconds()
        if age > self.stale_after_seconds:
            self._mark_stale(
                f"Last bar {last_bar_ts} is {age:.0f}s old while market is open"
            )
            return True

        if self.stale:
            logger.info("Market data recovered — last_bar=%s", last_bar_ts)
        self.stale = False
        self.last_event = None
        return False

    def _mark_stale(self, message: str) -> None:
        if not self.stale:
            logger.error("MARKET_DATA_STALE | %s", message)
        self.stale = True
        self.last_event = "MARKET_DATA_STALE"
