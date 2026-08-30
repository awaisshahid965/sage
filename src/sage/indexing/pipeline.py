"""Load, chunk, embed, store. The indexing half of retrieval.

This runs by hand -- `uv run poe index` -- and never at startup. An index is a
build artefact, like a compiled binary: made once from inputs that change
rarely, checked at boot, and used many times. Building it on boot would make
cold start scale with the corpus, re-pay the embedding bill on every container
restart, and put a provider outage between the process and its ability to
start.

The one thing here that is not obvious is where `dimensions` comes from. Not
from configuration, and not from asking the embedder: from `len()` of the first
vector it actually returns. A declared dimension count is a second copy of a
fact, written before anything has been embedded and therefore able to be wrong
-- and being wrong about it means a store configured for one vector width and
fed another. Measuring it removes the possibility.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sage.chunking.markdown import HeadingChunker
from sage.config import Settings
from sage.domain.retrieval import (
    Chunk,
    Chunker,
    Embedder,
    IndexManifest,
    SupportsPersistence,
    Vector,
    VectorRecord,
)
from sage.embeddings.factory import create_embedder
from sage.indexing.corpus import load_documents
from sage.logging import get_logger
from sage.vectorstores.factory import create_vector_store

log = get_logger(__name__)

# Texts per embedding request. Providers price and rate-limit per call, so one
# string at a time is the slowest and most expensive way to do this; but a
# whole corpus in one request eventually meets a payload or token ceiling.
EMBED_BATCH = 128


@dataclass(frozen=True, slots=True)
class IndexReport:
    """What a build did. Returned rather than printed, so it can be asserted."""

    documents: int
    chunks: int
    dimensions: int
    model_id: str
    chunker: str
    store: str


async def build_index(settings: Settings) -> IndexReport:
    """Build the index described by `settings` and write it to the store."""
    # Annotated as the port rather than the class, so the type checker
    # confirms `HeadingChunker` really satisfies `Chunker` here at the one
    # place they meet, instead of at no place at all.
    chunker: Chunker = HeadingChunker(max_chars=settings.chunk_max_chars)
    embedder = create_embedder(settings)
    store = create_vector_store(settings)

    documents = load_documents(settings.corpus_path)

    chunks: list[Chunk] = []
    for document in documents:
        produced = chunker.split(document)
        log.info("document_chunked", document=document.path, chunks=len(produced))
        chunks.extend(produced)

    if not chunks:
        raise ValueError("The corpus produced no chunks. Check the chunker.")

    vectors = await _embed(embedder, [chunk.text for chunk in chunks])
    dimensions = _one_width(vectors)

    manifest = IndexManifest(
        model_id=embedder.model_id,
        dimensions=dimensions,
        chunker=chunker.name,
        chunk_count=len(chunks),
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )

    records = [
        VectorRecord(chunk=chunk, vector=vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]

    await store.write(manifest, records)

    # Some stores need telling; a server-backed one persisted on write and has
    # nothing to do here. See `SupportsPersistence` for why this is a separate
    # protocol rather than a method every store must implement.
    if isinstance(store, SupportsPersistence):
        await store.persist()

    return IndexReport(
        documents=len(documents),
        chunks=len(chunks),
        dimensions=dimensions,
        model_id=embedder.model_id,
        chunker=chunker.name,
        store=settings.vector_store,
    )


async def _embed(embedder: Embedder, texts: Sequence[str]) -> list[Vector]:
    vectors: list[Vector] = []

    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        produced = await embedder.embed_documents(batch)

        # A provider that returns a different number of vectors than it was
        # given texts has silently dropped or merged something, and zipping
        # them afterwards would pair chunks with other chunks' embeddings.
        # Every answer would then cite the wrong document, with nothing
        # anywhere to suggest why.
        if len(produced) != len(batch):
            raise ValueError(
                f"Embedder returned {len(produced)} vectors for {len(batch)} texts."
            )

        vectors.extend(produced)

    return vectors


def _one_width(vectors: Sequence[Vector]) -> int:
    """The dimension count, insisting every vector agrees on it."""
    widths = {len(vector) for vector in vectors}

    if len(widths) != 1:
        raise ValueError(f"Embedder returned mixed vector widths: {sorted(widths)}.")

    return widths.pop()
