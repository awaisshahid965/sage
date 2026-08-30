"""Tests for the indexing pipeline and the wiring that consumes it.

These run the real corpus through the real chunker into a real store. Only the
embedder is a double, and that one is a real embedder too -- just a weak one.
So "retrieval works" is checked here as an actual claim about `data/pebble`
rather than about a fixture that agrees with itself.
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from sage.config import Settings
from sage.domain.context import Conversation
from sage.domain.llm import LLMError, Message
from sage.domain.retrieval import IndexMismatchError, Vector
from sage.embeddings.factory import BACKENDS, create_embedder
from sage.embeddings.hashing import HashingEmbedder
from sage.indexing.pipeline import build_index
from sage.main import create_app, lifespan
from sage.retrieval.dense import DenseRetriever
from sage.vectorstores.factory import STORES, create_vector_store


def retrieval_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Settings with retrieval on and the index somewhere disposable."""
    fields: dict[str, object] = {
        "environment": "test",
        "log_level": "WARNING",
        "llm_backend": "echo",
        "retrieval": True,
        "corpus_path": Path("data/pebble"),
        "embedding_backend": "hashing",
        "vector_store": "bruteforce",
        "index_path": tmp_path / "index",
    }
    return Settings(**(fields | overrides))  # type: ignore[arg-type]


# --- the pipeline ----------------------------------------------------------


async def test_building_an_index_covers_the_whole_corpus(tmp_path: Path) -> None:
    report = await build_index(retrieval_settings(tmp_path))

    assert report.documents == 8
    assert report.chunks > 50
    assert report.model_id == "hashing:v1:512"
    assert report.dimensions == 512


async def test_the_dimension_count_is_measured_not_declared(tmp_path: Path) -> None:
    """It comes from `len()` of a real vector. A configured value is a second
    copy of the fact, written before anything is embedded and free to be wrong."""
    report = await build_index(retrieval_settings(tmp_path))
    settings = retrieval_settings(tmp_path)

    store = create_vector_store(settings)
    manifest = await store.describe()

    assert manifest is not None
    assert manifest.dimensions == report.dimensions
    assert manifest.chunk_count == report.chunks


async def test_the_index_is_readable_by_the_next_process(tmp_path: Path) -> None:
    """An index is a build artefact: written by one process, read by another."""
    await build_index(retrieval_settings(tmp_path))

    # A completely fresh store object, as a restarted app would build.
    store = create_vector_store(retrieval_settings(tmp_path))
    retriever = DenseRetriever(HashingEmbedder(), store, top_k=3)

    hits = await retriever.retrieve(
        Conversation(question="how long is the warranty on a device?")
    )

    assert hits[0].chunk.doc_id == "POL-WAR-002"


async def test_retrieval_lands_on_the_right_section(tmp_path: Path) -> None:
    """Keyword queries, not natural questions, and that is not a shortcut.

    The hashing embedder has no IDF (see its module docstring), so a natural
    question is dominated by its stopwords and returns whichever chunk is
    richest in *how*, *long* and *do*. Asserting against natural questions here
    would be measuring that weakness rather than this pipeline.

    What these do check is the whole chain, honestly: the corpus loaded, split
    on its headings, embedded, written, read back and searched, landing on the
    exact section a citation would name. Whether "can I return these?" finds
    the hygiene clause is a question about a real embedding model, and it
    belongs to the eval work.
    """
    await build_index(retrieval_settings(tmp_path))
    store = create_vector_store(retrieval_settings(tmp_path))
    retriever = DenseRetriever(HashingEmbedder(), store, top_k=1)

    # Document and section, not the full citation string: a corpus version bump
    # would break the latter without anything about retrieval having changed.
    expected = {
        "restocking fee": ("POL-RET-001", "3"),
        "PebbleCare+ extended cover": ("POL-WAR-002", "4"),
        "dispatch cut-off time": ("POL-SHP-003", "1"),
        "trade-in valuation": ("POL-PAY-005", "6"),
        "promotional code stacking": ("POL-PAY-005", "4"),
    }

    for query, (doc_id, section) in expected.items():
        chunk = (await retriever.retrieve(Conversation(question=query)))[0].chunk
        assert (chunk.doc_id, chunk.section) == (doc_id, section), query


async def test_a_missing_corpus_says_so(tmp_path: Path) -> None:
    settings = retrieval_settings(tmp_path, corpus_path=tmp_path / "nowhere")

    with pytest.raises(FileNotFoundError, match="No corpus directory"):
        await build_index(settings)


class MiscountingEmbedder:
    """Returns fewer vectors than it was given texts."""

    @property
    def model_id(self) -> str:
        return "miscounting"

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [[1.0, 0.0]] * (len(texts) - 1)

    async def embed_query(self, text: str) -> Vector:
        return [1.0, 0.0]


async def test_a_short_batch_is_caught_rather_than_zipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zipping a short batch pairs chunks with other chunks' embeddings. Every
    answer then cites the wrong document, with nothing anywhere saying why."""
    monkeypatch.setattr(
        "sage.indexing.pipeline.create_embedder", lambda _: MiscountingEmbedder()
    )

    with pytest.raises(ValueError, match="vectors for"):
        await build_index(retrieval_settings(tmp_path))


# --- the factories ---------------------------------------------------------


def test_the_factories_reject_an_unknown_name() -> None:
    """`model_construct` skips validation, which is the only way to reach the
    factory's own error: the `Literal` on the setting normally rejects an
    unknown name first. Both guards are wanted — the config one for a typo in
    `.env`, this one for a builder that was never registered."""
    with pytest.raises(ValueError, match="Unknown embedding backend"):
        create_embedder(Settings.model_construct(embedding_backend="nope"))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Unknown vector store"):
        create_vector_store(Settings.model_construct(vector_store="nope"))  # type: ignore[arg-type]


def test_both_adapters_are_registered() -> None:
    assert BACKENDS == ("hashing", "langchain")
    assert STORES == ("bruteforce", "qdrant")


# --- the wiring ------------------------------------------------------------


async def test_retrieval_off_needs_no_index_and_no_embedder() -> None:
    """The default. A fresh clone boots and answers with nothing on disk."""
    settings = Settings(environment="test", log_level="WARNING", llm_backend="echo")
    app = create_app(settings)

    assert app.state.embedder is None
    assert app.state.vector_store is None

    async with lifespan(app):
        pass


async def test_retrieval_on_with_no_index_refuses_to_start(tmp_path: Path) -> None:
    app = create_app(retrieval_settings(tmp_path))

    with pytest.raises(IndexMismatchError, match="poe index"):
        async with lifespan(app):
            pass


async def test_an_index_from_another_embedder_refuses_to_start(
    tmp_path: Path,
) -> None:
    """The quiet failure this whole guard exists for. Without it the app
    starts, searches, and answers from passages drawn out of a different
    embedding space."""
    await build_index(retrieval_settings(tmp_path))

    app = create_app(
        retrieval_settings(tmp_path, embedding_backend="langchain", llm_api_key="x")
    )

    with pytest.raises(IndexMismatchError, match="not comparable"):
        async with lifespan(app):
            pass


async def test_a_matching_index_starts_and_answers(tmp_path: Path) -> None:
    await build_index(retrieval_settings(tmp_path))
    app = create_app(retrieval_settings(tmp_path))

    async with lifespan(app):
        answer = await app.state.sage.ask("how long is the warranty?")

    # `echo` repeats the last user message, which is the question — proving the
    # reference block went in *before* it and the frame held.
    assert answer.reply == "You said: how long is the warranty?"


async def test_the_retrieved_block_reaches_the_model(tmp_path: Path) -> None:
    """End to end with a recording model, through the app's own wiring."""
    from conftest import RecordingChatModel

    await build_index(retrieval_settings(tmp_path))
    app = create_app(retrieval_settings(tmp_path))

    model = RecordingChatModel()
    app.state.sage._model = model

    async with lifespan(app):
        await app.state.sage.ask("how long is the warranty on a device?")

    reference = [
        message
        for message in model.seen
        if message.role == "user" and "Reference material" in message.content
    ]

    assert len(reference) == 1
    assert "POL-WAR-002" in reference[0].content
    assert isinstance(model.seen[0], Message)
    assert model.seen[0].role == "system"


async def test_a_failing_embedder_surfaces_as_an_llm_error() -> None:
    """`langchain` with a model name that cannot be built. Reusing `LLMError`
    means `sage.main`'s existing 502 handler already covers embeddings."""
    with pytest.raises(LLMError):
        create_embedder(
            Settings(embedding_backend="langchain", embedding_model="nonsense:model")
        )
