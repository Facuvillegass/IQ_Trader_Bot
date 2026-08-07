"""SQLite lease lock — at most one trading worker may process the account."""

from __future__ import annotations

import logging
import os
import socket
import uuid
from datetime import datetime, timezone

from backend.app.db.database import Database
from backend.app.utils.iso import parse_utc, utc_iso

logger = logging.getLogger(__name__)

LEASE_TTL_SECONDS = 45


def make_owner_id() -> str:
    host = socket.gethostname()
    return f"{host}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class WorkerLease:
    def __init__(self, db: Database, ttl_seconds: int = LEASE_TTL_SECONDS):
        self.db = db
        self.ttl_seconds = ttl_seconds
        self.owner_id = make_owner_id()
        self.acquired = False

    def try_acquire(self) -> bool:
        now = datetime.now(timezone.utc)
        with self.db.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM worker_lease WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO worker_lease(id, owner_id, heartbeat_at, started_at, status)
                    VALUES (1, ?, ?, ?, 'ACTIVE')
                    """,
                    (self.owner_id, utc_iso(now), utc_iso(now)),
                )
                self.acquired = True
                logger.info("Worker lease acquired (new) owner=%s", self.owner_id)
                return True

            hb = parse_utc(row["heartbeat_at"])
            stale = (now - hb).total_seconds() > self.ttl_seconds
            released = str(row["status"] or "").upper() == "RELEASED"
            if row["owner_id"] == self.owner_id or stale or released:
                conn.execute(
                    """
                    UPDATE worker_lease
                    SET owner_id = ?, heartbeat_at = ?, started_at = ?, status = 'ACTIVE'
                    WHERE id = 1
                    """,
                    (self.owner_id, utc_iso(now), utc_iso(now)),
                )
                self.acquired = True
                logger.info(
                    "Worker lease acquired owner=%s stale=%s previous=%s",
                    self.owner_id,
                    stale,
                    row["owner_id"],
                )
                return True

            logger.warning(
                "Worker lease held by %s (heartbeat=%s) — this instance stays STANDBY",
                row["owner_id"],
                row["heartbeat_at"],
            )
            self.acquired = False
            return False

    def heartbeat(self) -> bool:
        if not self.acquired:
            return False
        now = utc_iso()
        with self.db.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """
                UPDATE worker_lease
                SET heartbeat_at = ?, status = 'ACTIVE'
                WHERE id = 1 AND owner_id = ?
                """,
                (now, self.owner_id),
            )
            if cur.rowcount != 1:
                self.acquired = False
                logger.error("Lost worker lease — stopping trading")
                return False
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE worker_lease
                SET status = 'RELEASED', heartbeat_at = ?, owner_id = ''
                WHERE id = 1 AND owner_id = ?
                """,
                (utc_iso(), self.owner_id),
            )
        self.acquired = False
        logger.info("Worker lease released owner=%s", self.owner_id)
