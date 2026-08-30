"""LangChain adapter for embeddings.

The same shape as `sage.llm.langchain`, and for the same reason:
`init_embeddings` takes a "<provider>:<model>" string, so changing provider is
a config change and nothing else.

    SAGE_EMBEDDING_MODEL=openai:text-embedding-3-small
    SAGE_EMBEDDING_MODEL=ollama:nomic-embed-text
    SAGE_EMBEDDING_MODEL=cohere:embed-english-v3.0

Install that provider's package first, as with chat models.

One warning that this adapter cannot enforce for you. Some of the models
reachable through this string -- Nomic and the E5/BGE families in particular --
are *asymmetric*: they expect `search_document:` and `search_query:` prefixes,
and LangChain's generic wrapper does not add them. Pointed at one of those,
this class embeds both sides identically and retrieval quietly gets worse with
no error anywhere. That is exactly the case `Embedder`'s two methods exist for,
and the fix is a sibling adapter that adds the prefixes -- not a flag here.
"""

from collections.abc import Sequence
from typing import Any

from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings

from sage.config import Settings
from sage.domain.llm import LLMError
from sage.domain.retrieval import Embedder, Vector


class LangChainEmbedder:
    """Wraps a LangChain embeddings object so it satisfies `Embedder`.

    Takes an already-built model rather than building one, so the translation
    is testable with a fake and all the config reading stays in `build`.
    """

    def __init__(self, model_id: str, embeddings: Embeddings) -> None:
        self._model_id = model_id
        self._embeddings = embeddings

    @property
    def model_id(self) -> str:
        return self._model_id

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        try:
            vectors = await self._embeddings.aembed_documents(list(texts))
        except Exception as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        return list(vectors)

    async def embed_query(self, text: str) -> Vector:
        try:
            return await self._embeddings.aembed_query(text)
        except Exception as exc:
            # Reusing `LLMError` rather than minting an `EmbeddingError`. Both
            # are "the provider did not answer", both want the same 502, and
            # `sage.main` already has one handler for it. A second exception
            # type would need a second handler that did the identical thing.
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc


def build(settings: Settings) -> Embedder:
    """Build a LangChain-backed embedder from settings."""
    kwargs: dict[str, Any] = {}

    # Both optional, exactly as for chat models: with no key the provider SDK
    # falls back to its own environment variable.
    if settings.llm_api_key is not None:
        kwargs["api_key"] = settings.llm_api_key.get_secret_value()
    if settings.llm_base_url is not None:
        kwargs["base_url"] = settings.llm_base_url

    try:
        embeddings = init_embeddings(settings.embedding_model, **kwargs)
    except Exception as exc:
        raise LLMError(
            f"Could not build embedder {settings.embedding_model!r}: {exc}"
        ) from exc

    return LangChainEmbedder(settings.embedding_model, embeddings)
