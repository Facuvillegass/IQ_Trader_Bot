"""Standalone trading worker entrypoint (optional; Railway uses embedded worker).

Use this only if you split worker and API into two processes that share the
same persistent SQLite volume. The lease lock still guarantees a singleton.
"""

from __future__ import annotations

import logging
import signal
import time

from backend.app.config import get_settings
from backend.app.db.database import Database
from backend.app.engine.worker import TradingWorker
from backend.app.runtime import RUNTIME
from backend.app.utils.iso import utc_iso
from backend.app.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.logs_path)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.reports_path.mkdir(parents=True, exist_ok=True)

    if settings.trading_mode != "PAPER":
        raise RuntimeError("Refusing to start: TRADING_MODE must be PAPER")

    RUNTIME.started_at = utc_iso()
    db = Database(settings.db_path)
    worker = TradingWorker(db, settings)
    worker.start()

    stop = False

    def _handle(_sig, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    logger.info("Standalone worker running db=%s", settings.db_path)
    while not stop:
        time.sleep(1)
    worker.stop()
    logger.info("Standalone worker stopped")


if __name__ == "__main__":
    main()
