"""Append-only logging to system / trading / errors files."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    # Quiet console — only warnings+
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    root.addHandler(console)

    system_handler = RotatingFileHandler(
        log_dir / "system.log", maxBytes=5_000_000, backupCount=5
    )
    system_handler.setLevel(logging.INFO)
    system_handler.setFormatter(fmt)
    root.addHandler(system_handler)

    trading_logger = logging.getLogger("trading")
    trading_handler = RotatingFileHandler(
        log_dir / "trading.log", maxBytes=5_000_000, backupCount=10
    )
    trading_handler.setLevel(logging.INFO)
    trading_handler.setFormatter(fmt)
    trading_logger.addHandler(trading_handler)
    trading_logger.propagate = True

    error_handler = RotatingFileHandler(
        log_dir / "errors.log", maxBytes=5_000_000, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)
