"""Tests for the retrieval seam: embedder, stores, guard, retriever.

Every test here runs offline. The hashing embedder needs no key and Qdrant's
local mode needs no container, so the whole path is exercised for free -- which
is the reason both of those exist.

The store tests are parametrised over both implementations on purpose. A port
with two adapters is only real if the same test passes against each, and the
one thing that must not differ between an exact store and an approximate one is
what they *mean*.
"""

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient

from sage.domain.context import Conversation
from sage.domain.retrieval import (
    Chunk,
    Hit,
    IndexManifest,
    IndexMismatchError,
    SupportsPersistence,
    Vector,
    VectorRecord,
    VectorStore,
)
from sage.embeddings.hashing import HashingEmbedder
from sage.retrieval.dense import DenseRetriever
from sage.retrieval.guard import verify_index
from sage.vectorstores.bruteforce import BruteForceStore
from sage.vectorstores.qdrant import QdrantStore

TEXTS = {
    "returns": "Returns and Refunds Policy > 1. Returns close 30 days after delivery.",
    "warranty": "Warranty Policy > 1. Devices carry a 24 month warranty period.",
    "shipping": "Shipping Policy > 2. United Kingdom delivery takes 3 to 5 days.",
}


def chunk_for(key: str, index: int) -> Chunk:
    return Chunk(
        id=f"chunk-{key}",
        text=TEXTS[key],
        doc_id=f"POL-{key.upper()}",
        title=key.title(),
        version="1.0",
        section="1",
        heading=f"1. {key.title()}",
        ordinal=index,
        source=f"{key}.md",
    )


async def records() -> list[VectorRecord]:
    embedder = HashingEmbedder()
    keys = list(TEXTS)
    vectors = await embedder.embed_documents([TEXTS[key] for key in keys])

    return [
        VectorRecord(chunk=chunk_for(key, index), vector=vector)
        for index, (key, vector) in enumerate(zip(keys, vectors, strict=True))
    ]


def manifest_for(dimensions: int, count: int, model_id: str) -> IndexManifest:
    return IndexManifest(
        model_id=model_id,
        dimensions=dimensions,
        chunker="test",
        chunk_count=count,
        built_at="2026-01-01T00:00:00+00:00",
    )


@pytest.fixture(params=["bruteforce", "qdrant"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[VectorStore]:
    """One of each implementation, so every test below runs twice."""
    if request.param == "bruteforce":
        yield BruteForceStore()
    else:
        client = AsyncQdrantClient(location=":memory:")
        yield QdrantStore(client, "test")
        await client.close()


# --- the embedder ----------------------------------------------------------


async def test_the_same_text_always_embeds_the_same_way() -> None:
    """Python randomises `hash()` per process. An embedder that used it would
    build an index the next process could not read, and the symptom would look
    like bad retrieval rather than like a bug."""
    first = await HashingEmbedder().embed_query("returns close after 30 days")
    second = await HashingEmbedder().embed_query("returns close after 30 days")

    assert list(first) == list(second)


async def test_shared_words_point_in_similar_directions() -> None:
    """The property that makes this a test double rather than noise: an
    assertion about which passage came back has to be able to mean something."""
    embedder = HashingEmbedder()
    query = await embedder.embed_query("how long is the warranty period")
    vectors = await embedder.embed_documents(list(TEXTS.values()))

    scores = [
        sum(a * b for a, b in zip(query, vector, strict=True)) for vector in vectors
    ]

    assert scores.index(max(scores)) == list(TEXTS).index("warranty")


async def test_a_text_with_no_words_embeds_to_zero_rather_than_failing() -> None:
    vector = await HashingEmbedder().embed_query("!!! ???")

    assert set(vector) == {0.0}


# --- the stores ------------------------------------------------------------


async def test_a_fresh_store_has_no_manifest(store: VectorStore) -> None:
    """`None` means "run the indexer", and it is a different answer from a
    manifest that disagrees with the running embedder."""
    assert await store.describe() is None


async def test_a_fresh_store_searches_without_exploding(store: VectorStore) -> None:
    assert list(await store.search([0.1] * 512, 5)) == []


async def test_writing_stores_the_manifest_with_the_vectors(store: VectorStore) -> None:
    written = await records()
    manifest = manifest_for(512, len(written), "hashing:v1:512")

    await store.write(manifest, written)

    assert await store.describe() == manifest


async def test_search_ranks_the_matching_passage_first(store: VectorStore) -> None:
    written = await records()
    await store.write(manifest_for(512, len(written), "hashing:v1:512"), written)

    query = await HashingEmbedder().embed_query("how long is the warranty period")
    hits = await store.search(query, 3)

    assert hits[0].chunk.doc_id == "POL-WARRANTY"
    assert hits[0].chunk.citation == "POL-WARRANTY v1.0 §1"


async def test_search_returns_at_most_k(store: VectorStore) -> None:
    written = await records()
    await store.write(manifest_for(512, len(written), "hashing:v1:512"), written)

    query = await HashingEmbedder().embed_query("returns")

    assert len(await store.search(query, 2)) == 2
    # More than there are is not an error; there are simply only three.
    assert len(await store.search(query, 99)) == 3


async def test_scores_come_back_in_descending_order(store: VectorStore) -> None:
    written = await records()
    await store.write(manifest_for(512, len(written), "hashing:v1:512"), written)

    query = await HashingEmbedder().embed_query("warranty period for devices")
    scores = [hit.score for hit in await store.search(query, 3)]

    assert scores == sorted(scores, reverse=True)


async def test_writing_replaces_rather_than_appends(store: VectorStore) -> None:
    """Appending leaves orphans: delete a section from a policy and its chunk
    stays retrievable forever, citing a rule that no longer exists."""
    written = await records()
    await store.write(manifest_for(512, len(written), "hashing:v1:512"), written)

    await store.write(manifest_for(512, 1, "hashing:v1:512"), written[:1])

    query = await HashingEmbedder().embed_query("warranty period for devices")
    hits = await store.search(query, 99)

    assert [hit.chunk.doc_id for hit in hits] == ["POL-RETURNS"]


async def test_the_whole_chunk_survives_the_round_trip(store: VectorStore) -> None:
    """A store that returned ids would force a second lookup table on every
    caller, and that table would eventually fall out of step with the index."""
    written = await records()
    await store.write(manifest_for(512, len(written), "hashing:v1:512"), written)

    query = await HashingEmbedder().embed_query("returns close 30 days delivery")
    hit = (await store.search(query, 1))[0]

    assert hit.chunk == written[0].chunk


# --- persistence -----------------------------------------------------------


async def test_the_brute_force_index_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "index"
    written = await records()
    manifest = manifest_for(512, len(written), "hashing:v1:512")

    original = BruteForceStore(path=path)
    await original.write(manifest, written)
    assert isinstance(original, SupportsPersistence)
    await original.persist()

    reopened = BruteForceStore(path=path)
    reopened.load()

    assert await reopened.describe() == manifest

    query = await HashingEmbedder().embed_query("how long is the warranty period")
    assert (await reopened.search(query, 1))[0].chunk.doc_id == "POL-WARRANTY"


async def test_loading_a_missing_index_is_not_an_error(tmp_path: Path) -> None:
    store = BruteForceStore(path=tmp_path / "nothing-here")
    store.load()

    assert await store.describe() is None


# --- the staleness guard ---------------------------------------------------


async def test_the_guard_rejects_a_missing_index() -> None:
    with pytest.raises(IndexMismatchError, match="no index"):
        await verify_index(BruteForceStore(), HashingEmbedder())


async def test_the_guard_rejects_an_index_from_another_model() -> None:
    """The failure this exists for. Nothing raises without it: vectors go in,
    neighbours come out, and the answers are quietly drawn from the wrong
    passages because two embedding spaces were compared."""
    store = BruteForceStore()
    written = await records()
    await store.write(
        manifest_for(512, len(written), "openai:text-embedding-3-small"), written
    )

    with pytest.raises(IndexMismatchError, match="not comparable"):
        await verify_index(store, HashingEmbedder())


async def test_the_guard_passes_a_matching_index() -> None:
    store = BruteForceStore()
    written = await records()
    manifest = manifest_for(512, len(written), HashingEmbedder().model_id)
    await store.write(manifest, written)

    assert await verify_index(store, HashingEmbedder()) == manifest


# --- the retriever ---------------------------------------------------------


class RecordingStore:
    """A `VectorStore` that reports what it was asked for."""

    def __init__(self) -> None:
        self.k: int | None = None

    async def describe(self) -> IndexManifest | None:
        return None

    async def write(
        self, manifest: IndexManifest, records: Sequence[VectorRecord]
    ) -> None: ...

    async def search(self, vector: Vector, k: int) -> Sequence[Hit]:
        self.k = k
        return [Hit(chunk=chunk_for("returns", 0), score=0.9)]


async def test_the_retriever_asks_for_top_k() -> None:
    store = RecordingStore()
    retriever = DenseRetriever(HashingEmbedder(), store, top_k=7)

    await retriever.retrieve(Conversation(question="how long do returns take?"))

    assert store.k == 7


async def test_the_retriever_searches_with_the_question() -> None:
    store = BruteForceStore()
    written = await records()
    await store.write(manifest_for(512, len(written), "hashing:v1:512"), written)

    retriever = DenseRetriever(HashingEmbedder(), store, top_k=1)
    hits = await retriever.retrieve(
        Conversation(question="what is the warranty period for devices?")
    )

    assert [hit.chunk.doc_id for hit in hits] == ["POL-WARRANTY"]
