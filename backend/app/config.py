"""Application configuration. Strategy parameters are intentionally frozen."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    trading_mode: Literal["PAPER"] = "PAPER"
    data_provider: Literal["mock", "databento", "yfinance", "replay"] = "mock"

    databento_api_key: str = ""
    data_api_key: str = ""
    tradovate_username: str = ""
    tradovate_password: str = ""
    tradovate_client_id: str = ""
    tradovate_client_secret: str = ""
    tradovate_account_id: str = ""

    initial_balance: float = 10_000.0
    sma_period: int = 4750
    band_points: float = 50.0
    quantity: int = Field(
        default=1,
        validation_alias=AliasChoices("quantity", "QUANTITY", "MNQ_QUANTITY"),
    )
    commission_per_side: float = 0.62
    slippage_ticks: int = 1

    # MNQ contract specs (CME)
    tick_size: float = 0.25
    tick_value: float = 0.50
    point_value: float = 2.0
    symbol: str = "MNQ"

    database_path: str = "data/paper_trading.db"
    log_dir: str = "logs"
    reports_dir: str = "reports"

    api_host: str = "0.0.0.0"
    api_port: int = 8010
    frontend_port: int = 5173
    tz_display: str = "America/Argentina/Cordoba"
    stale_after_seconds: int = 180
    embed_worker: bool = True
    worker_lease_ttl_seconds: int = 45

    bars_required_to_trade: int = 4750
    exit_on_session_close: bool = True
    exit_on_session_close_seconds: int = 30
    engine_poll_seconds: int = 5
    forward_test_enabled: bool = True
    sanity_check_year: int = 2024

    # CME equity index ETH: Sun 17:00 CT → Fri 16:00 CT, daily break 16:00–17:00 CT
    session_timezone: str = "America/Chicago"
    session_break_hour: int = 16
    session_break_minute: int = 0
    session_resume_hour: int = 17
    session_resume_minute: int = 0

    @field_validator("trading_mode")
    @classmethod
    def paper_only(cls, value: str) -> str:
        if value != "PAPER":
            raise ValueError(
                "TRADING_MODE must be PAPER. Live trading is intentionally blocked."
            )
        return value

    @property
    def db_path(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def logs_path(self) -> Path:
        path = Path(self.log_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def reports_path(self) -> Path:
        path = Path(self.reports_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def resolved_data_api_key(self) -> str:
        return (self.databento_api_key or self.data_api_key or "").strip()

    @property
    def bind_port(self) -> int:
        import os

        return int(os.environ.get("PORT", self.api_port))

    @property
    def slippage_points(self) -> float:
        return self.slippage_ticks * self.tick_size

    @property
    def slippage_cost_per_side(self) -> float:
        return self.slippage_ticks * self.tick_value * self.quantity


@lru_cache
def get_settings() -> Settings:
    return Settings()
