"""Application settings, loaded from the environment and `.env`.

Typed configuration is the Python answer to a validated `process.env`: every
setting is declared once, coerced to the right type, and validated at startup
rather than at first use.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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

    # --- LLM ---------------------------------------------------------------
    # Which adapter runs. "echo" is the default so the app boots and answers
    # with no key and no network. Set SAGE_LLM_BACKEND=langchain to go live.
    llm_backend: Literal["langchain", "echo"] = "echo"

    # "<provider>:<model>". This is the provider switch: change the prefix and
    # no code moves. Install that provider's package first, e.g.
    #   uv add langchain-anthropic
    #   SAGE_LLM_MODEL=anthropic:claude-haiku-4-5-20251001
    llm_model: str = "openai:gpt-4o-mini"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # Optional. Left unset, each provider SDK reads its own env var
    # (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...). SecretStr keeps the value out
    # of logs and tracebacks.
    llm_api_key: SecretStr | None = None

    # Optional. Any OpenAI-compatible server: Ollama, vLLM, OpenRouter, a proxy.
    llm_base_url: str | None = None

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
