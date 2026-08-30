"""Chooses an embedder by name at startup.

Same shape as `sage.llm.factory`: write a class with `model_id`,
`embed_documents` and `embed_query`, give its module a `build` function, add a
line to `_BUILDERS`.
"""

from collections.abc import Callable

from sage.config import Settings
from sage.domain.retrieval import Embedder
from sage.embeddings import hashing, langchain

Builder = Callable[[Settings], Embedder]

_BUILDERS: dict[str, Builder] = {
    "hashing": hashing.build,
    "langchain": langchain.build,
}

BACKENDS = tuple(sorted(_BUILDERS))


def create_embedder(settings: Settings) -> Embedder:
    """Return the embedder named by `settings.embedding_backend`."""
    try:
        build = _BUILDERS[settings.embedding_backend]
    except KeyError:
        raise ValueError(
            f"Unknown embedding backend {settings.embedding_backend!r}. "
            f"Known backends: {', '.join(BACKENDS)}."
        ) from None

    return build(settings)
