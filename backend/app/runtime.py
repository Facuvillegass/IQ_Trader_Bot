"""Shared runtime snapshot for health / dashboard (UTC)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RuntimeState:
    started_at: str = ""
    worker_alive: bool = False
    worker_ready: bool = False
    worker_status: str = "INIT"
    market_data_connected: bool = False
    market_data_stale: bool = False
    last_bar_time: Optional[str] = None
    last_signal_time: Optional[str] = None
    last_error: Optional[str] = None
    database_ok: bool = False
    lease_owner: Optional[str] = None
    standby: bool = False
    entries_blocked: bool = False

    def uptime_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        try:
            start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            return max(0.0, (datetime.now(timezone.utc) - start).total_seconds())
        except Exception:
            return 0.0


RUNTIME = RuntimeState()
