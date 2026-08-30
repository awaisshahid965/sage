"""Chooses a vector store by name at startup.

Same shape as `sage.llm.factory` and `sage.conversations.factory`: write a
class with `describe`, `write` and `search`, give its module a `build`
function, add a line to `_BUILDERS`.

The two entries here are not a default and a fallback. `bruteforce` is exact
and `qdrant` is approximate, and the point of having both behind one name is
that `poe bench` can run the same questions through each and report what the
approximation costs.
"""

from collections.abc import Callable

from sage.config import Settings
from sage.domain.retrieval import VectorStore
from sage.vectorstores import bruteforce, qdrant

Builder = Callable[[Settings], VectorStore]

_BUILDERS: dict[str, Builder] = {
    "bruteforce": bruteforce.build,
    "qdrant": qdrant.build,
}

STORES = tuple(sorted(_BUILDERS))


def create_vector_store(settings: Settings) -> VectorStore:
    """Return the store named by `settings.vector_store`."""
    try:
        build = _BUILDERS[settings.vector_store]
    except KeyError:
        raise ValueError(
            f"Unknown vector store {settings.vector_store!r}. "
            f"Known stores: {', '.join(STORES)}."
        ) from None

    return build(settings)
