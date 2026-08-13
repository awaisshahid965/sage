"""Application settings, loaded from the environment and `.env`.

Typed configuration is the Python answer to a validated `process.env`: every
setting is declared once, coerced to the right type, and validated at startup
rather than at first use.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings resolved from environment variables, then `.env`, then defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SAGE_",
        extra="ignore",
    )

    app_name: str = "sage"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8000

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so the environment is read once. Call `get_settings.cache_clear()`
    in tests that need to swap the environment out from under it.
    """
    return Settings()
