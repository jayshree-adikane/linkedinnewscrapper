"""Central, environment-driven configuration.

All values can be overridden with ``LPS_*`` environment variables. Nothing
secret (passwords, cookies, tokens) is ever read from or written to config.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the application."""

    output_dir: Path
    log_dir: Path
    user_data_dir: Path
    max_profiles_default: int = 25
    max_profiles_hard_cap: int = 100
    min_delay_seconds: float = 5.0
    delay_seconds: float = 10.0
    page_timeout_ms: int = 30_000
    login_timeout_seconds: int = 300
    max_retries: int = 2
    backoff_base_seconds: float = 3.0
    headless: bool = False
    output_filename: str = "linkedin_prospects_output.xlsx"
    errors_filename: str = "linkedin_prospects_errors.xlsx"
    checkpoint_filename: str = "checkpoint.jsonl"

    @property
    def output_path(self) -> Path:
        return self.output_dir / self.output_filename

    @property
    def errors_path(self) -> Path:
        return self.output_dir / self.errors_filename

    @property
    def checkpoint_path(self) -> Path:
        return self.output_dir / self.checkpoint_filename

    def ensure_dirs(self) -> None:
        """Create output/log directories if they do not exist."""
        for path in (self.output_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build the configuration from environment variables."""
        return cls(
            output_dir=Path(os.environ.get("LPS_OUTPUT_DIR", BASE_DIR / "output")),
            log_dir=Path(os.environ.get("LPS_LOG_DIR", BASE_DIR / "logs")),
            user_data_dir=Path(
                os.environ.get("LPS_USER_DATA_DIR", BASE_DIR / ".browser-profile")
            ),
            max_profiles_default=_env_int("LPS_MAX_PROFILES", 25),
            max_profiles_hard_cap=_env_int("LPS_MAX_PROFILES_HARD_CAP", 100),
            min_delay_seconds=_env_float("LPS_MIN_DELAY_SECONDS", 5.0),
            delay_seconds=_env_float("LPS_DELAY_SECONDS", 10.0),
            page_timeout_ms=_env_int("LPS_PAGE_TIMEOUT_MS", 30_000),
            login_timeout_seconds=_env_int("LPS_LOGIN_TIMEOUT_SECONDS", 300),
            max_retries=_env_int("LPS_MAX_RETRIES", 2),
            backoff_base_seconds=_env_float("LPS_BACKOFF_BASE_SECONDS", 3.0),
            headless=_env_bool("LPS_HEADLESS", False),
        )
