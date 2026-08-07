"""UTC-first timestamp helpers. Server local TZ is never source of truth."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

UTC = ZoneInfo("UTC")
CT = ZoneInfo("America/Chicago")
AR = ZoneInfo("America/Argentina/Cordoba")


def parse_utc(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        dt = ts
    else:
        dt = date_parser.isoparse(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_iso(ts: str | datetime | None = None) -> str:
    if ts is None:
        dt = datetime.now(timezone.utc)
    else:
        dt = parse_utc(ts)
    return dt.replace(microsecond=0).isoformat()


def ar_display(ts: str | datetime | None) -> str:
    if ts is None:
        return ""
    dt = parse_utc(ts).astimezone(AR)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + " ART"


def ct_display(ts: str | datetime | None) -> str:
    if ts is None:
        return ""
    dt = parse_utc(ts).astimezone(CT)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + " CT"
