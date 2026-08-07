"""CME equity-index ETH session helpers (NinjaTrader-consistent).

MNQ ETH:
- Open: Sunday 17:00 America/Chicago
- Close / daily break: Monday–Friday 16:00 America/Chicago
- Resume: 17:00 America/Chicago
- Weekend: Friday 16:00 → Sunday 17:00 closed

Exit on session close seconds = 30 → flatten at 15:59:30 CT.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")


def to_ct(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        # Assume UTC if naive
        ts = ts.replace(tzinfo=ZoneInfo("UTC"))
    return ts.astimezone(CT)


def is_weekend_closed(ts_ct: datetime) -> bool:
    # Friday after 16:00 through Sunday before 17:00
    weekday = ts_ct.weekday()  # Mon=0 ... Sun=6
    t = ts_ct.time()
    if weekday == 4 and t >= time(16, 0):
        return True
    if weekday == 5:
        return True
    if weekday == 6 and t < time(17, 0):
        return True
    return False


def is_daily_break(ts_ct: datetime) -> bool:
    """True during Mon–Thu 16:00–17:00 CT maintenance break."""
    weekday = ts_ct.weekday()
    if weekday > 4:
        return False
    t = ts_ct.time()
    return time(16, 0) <= t < time(17, 0)


def is_market_open(ts: datetime) -> bool:
    ts_ct = to_ct(ts)
    if is_weekend_closed(ts_ct):
        return False
    if is_daily_break(ts_ct):
        return False
    return True


def session_close_exit_time(ts: datetime, seconds_before: int = 30) -> Optional[datetime]:
    """Return today's session-close exit timestamp in CT if relevant for this bar day."""
    ts_ct = to_ct(ts)
    if ts_ct.weekday() > 4:
        return None
    close = ts_ct.replace(hour=16, minute=0, second=0, microsecond=0)
    return close - timedelta(seconds=seconds_before)


def should_exit_for_session_close(
    bar_ts: datetime,
    *,
    seconds_before: int = 30,
    enabled: bool = True,
) -> bool:
    """True if this closed 1m bar is the last actionable bar before session close.

    For 1-minute bars, the bar starting at 15:58 CT closes at 15:59.
    With ExitOnSessionCloseSeconds=30, Ninja conceptually exits near 15:59:30.
    We treat the 15:59 CT bar close (bar_ts labeled as start or end) carefully.

    Convention in this system: bar_ts is the bar OPEN time (left label).
    So the bar that closes at 15:59:00 has bar_ts=15:58:00, and the bar that
    includes 15:59:30 would be bar_ts=15:59:00 (open 15:59, close 16:00).

    We exit on the bar with open == 15:59 CT (closes at session break), which
    is the last completed minute before the break when evaluated on that bar's close.
    """
    if not enabled:
        return False
    ts_ct = to_ct(bar_ts)
    if ts_ct.weekday() > 4:
        return False
    # Exit on the 15:59 bar (open), i.e. when close reaches 16:00 session break.
    # With seconds_before=30 this is the practical 1-minute approximation.
    target = ts_ct.replace(hour=15, minute=59, second=0, microsecond=0)
    return ts_ct.replace(second=0, microsecond=0) == target
