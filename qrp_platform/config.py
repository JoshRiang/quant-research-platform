"""Pydantic settings for the quant research qrp_platform."""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / .env."""

    # Paper trading
    paper_capital: float = 100_000.0
    paper_cron: str = "0 9 * * 1-5"  # 9am Mon–Fri

    # Paths
    data_dir: Path = Path("./data")
    results_dir: Path = Path("./results")

    # Logging / server
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Backtest defaults
    default_start: str = "2018-01-01"
    default_end: str = "2024-01-01"

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()