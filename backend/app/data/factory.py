"""Provider factory."""

from __future__ import annotations

from pathlib import Path

from backend.app.config import ROOT_DIR, Settings
from backend.app.data.provider import MarketDataProvider


def create_provider(settings: Settings) -> MarketDataProvider:
    if settings.data_provider == "mock":
        from backend.app.data.mock_provider import MockProvider

        return MockProvider()

    if settings.data_provider == "databento":
        from backend.app.data.databento_provider import DatabentoProvider

        return DatabentoProvider(api_key=settings.resolved_data_api_key)

    if settings.data_provider == "yfinance":
        from backend.app.data.yfinance_provider import YFinanceProvider

        return YFinanceProvider()

    if settings.data_provider == "replay":
        from backend.app.data.replay_provider import ReplayProvider

        return ReplayProvider(ROOT_DIR / "data" / "raw" / "mnq_1m.csv")

    raise ValueError(f"Unknown DATA_PROVIDER: {settings.data_provider}")
