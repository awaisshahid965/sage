"""The check that stops a stale index being served.

Worth stating the failure this prevents, because it is the one that does not
look like a failure.

Swap the embedding model and restart without re-indexing. The store still
holds vectors. The query still produces a vector. The search still returns k
neighbours, with plausible-looking scores, and the model still writes a
confident answer citing a real document id. Nothing raises, nothing logs, and
no test fails — the passages are simply the wrong ones, because a point from
one embedding space was compared against points from another. Retrieval quality
collapses and there is no error anywhere to lead you to why.

It costs one string comparison at startup to make that impossible. Running it
at startup rather than per query means the process either serves a coherent
index or refuses to serve at all, and a developer who has just changed a model
finds out immediately instead of from a stranger's bad answer.
"""

from sage.domain.retrieval import (
    Embedder,
    IndexManifest,
    IndexMismatchError,
    VectorStore,
)
from sage.logging import get_logger

log = get_logger(__name__)


async def verify_index(store: VectorStore, embedder: Embedder) -> IndexManifest:
    """Return the index's manifest, or raise if it cannot be trusted.

    Two failures, kept apart because they have different fixes: there is no
    index (build one) and there is an index from a different model (rebuild
    it). Collapsing them into "index problem" would leave the reader to work
    out which.
    """
    manifest = await store.describe()

    if manifest is None:
        raise IndexMismatchError(
            "Retrieval is on but no index has been built. Run `uv run poe index`."
        )

    if manifest.model_id != embedder.model_id:
        raise IndexMismatchError(
            f"The index was built with {manifest.model_id!r} but the running "
            f"embedder is {embedder.model_id!r}. Vectors from two models are "
            f"not comparable. Rebuild with `uv run poe index`."
        )

    log.info(
        "index_verified",
        model_id=manifest.model_id,
        dimensions=manifest.dimensions,
        chunks=manifest.chunk_count,
        chunker=manifest.chunker,
        built_at=manifest.built_at,
    )
    return manifest
