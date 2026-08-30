"""Application settings, loaded from the environment and `.env`.

Typed configuration is the Python answer to a validated `process.env`: every
setting is declared once, coerced to the right type, and validated at startup
rather than at first use.
"""

from functools import lru_cache
from pathlib import Path
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

    # --- Conversations -----------------------------------------------------
    # Where conversations live between requests. "memory" is the default for
    # the same reason "echo" is: the app boots and the suite passes with no
    # infrastructure at all. docker-compose sets this to "redis".
    conversation_store: Literal["memory", "redis"] = "memory"

    redis_url: str = "redis://localhost:6379/0"

    # How long a conversation survives *silence*. The clock restarts on every
    # exchange, so this is not a cap on how long a conversation may run — it is
    # how long an abandoned one lingers. A day, matching the eviction policy
    # the Redis service is configured with.
    conversation_ttl_seconds: int = Field(default=86_400, gt=0)

    # --- Retrieval ---------------------------------------------------------
    # Off by default, like every other piece of infrastructure here: a fresh
    # clone boots, answers, and passes its tests with no index on disk and no
    # embedding provider configured. Turning it on with no index built is a
    # startup failure, not a silent degradation — see `sage.retrieval.guard`.
    retrieval: bool = False

    corpus_path: Path = Path("data/pebble")

    # The size backstop for a section that will not fit in one chunk. Roughly
    # 450 tokens. Most sections in the corpus come in under it and stay whole.
    chunk_max_chars: int = Field(default=1800, gt=0)

    # "hashing" is to embeddings what "echo" is to chat models: offline, free,
    # and good enough to assert against. It is a test double, not a fallback.
    embedding_backend: Literal["hashing", "langchain"] = "hashing"

    # "<provider>:<model>", same convention as `llm_model`. Reuses
    # `llm_api_key` and `llm_base_url`, since in practice the embedding and
    # chat providers are the same account.
    embedding_model: str = "openai:text-embedding-3-small"

    # "bruteforce" is exact and is the oracle the approximate store is measured
    # against. "qdrant" is HNSW.
    vector_store: Literal["bruteforce", "qdrant"] = "bruteforce"

    # Where `bruteforce` keeps its index between runs. Ignored by `qdrant`,
    # which persists itself.
    index_path: Path = Path("data/index")

    # ":memory:" or a filesystem path runs Qdrant in-process, which is how the
    # test suite reaches it without a container. An http(s) URL is a server.
    qdrant_url: str = ":memory:"
    qdrant_collection: str = "pebble"

    # Kilobytes of vector data below which Qdrant skips the HNSW graph and
    # scans exhaustively — which for a collection this size is the faster and
    # more accurate choice, and is what its 10 MB default will do here. Set to
    # 0 to force the graph on regardless. Left at Qdrant's default unless
    # something says otherwise, so that turning approximation on is a decision
    # rather than an assumption. See `sage.vectorstores.qdrant`.
    qdrant_full_scan_threshold: int | None = None

    retrieval_top_k: int = Field(default=5, gt=0)

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
