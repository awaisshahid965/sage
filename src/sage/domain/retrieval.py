"""The retrieval ports.

Four seams, not one, because "answer from the documents" is four jobs that
change for unrelated reasons:

    Chunker     how a document is cut up          indexing only
    Embedder    text -> vector                    indexing *and* query
    VectorStore vectors in, nearest ones out      indexing (write), query (read)
    Retriever   question -> passages              query only

Splitting them is what makes any one replaceable. Heading-aware chunking gives
way to semantic chunking without the store noticing; brute force gives way to
HNSW without the embedder noticing; a reranker slots in front of the store
without the context strategy noticing.

Two rules hold the whole thing together.

**The store takes vectors, never text.** It is nearest-neighbour search over
float arrays with metadata attached, and it does not know an embedder exists.
The alternative -- a store that embeds for you -- makes every store adapter
re-implement embedding and turns "swap the embedder" into a change in two
places. It also matches the metal: Qdrant, pgvector and FAISS do not embed.

**Embedding a document and embedding a question are different operations.**
OpenAI's models happen to treat them alike. E5, BGE, Nomic and Gemini do not --
they want a `passage:`/`query:` prefix or a task-type flag, and getting it wrong
costs recall silently, with no error to notice. So `Embedder` has two methods.
A symmetric adapter points both at the same call and loses nothing; an
asymmetric one is then a new class rather than a change to this file.

`Retriever` is the seam people skip. Without it, `Passages` would embed, search
and format, and adding a reranker or hybrid search would mean rewriting a
context strategy. With it, `Passages` only formats.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from sage.domain.context import Conversation

# A point in embedding space. `Sequence[float]` rather than a numpy array
# because the port must not drag numpy into every adapter that satisfies it --
# the brute-force store wants arrays, an HTTP client wants a plain list, and
# both are this.
Vector = Sequence[float]


@dataclass(frozen=True, slots=True)
class Document:
    """A source file, before anything has been done to it.

    Deliberately just bytes and a path. Front matter is not parsed here because
    parsing it is a markdown fact, and markdown is the chunker's business -- a
    later `HtmlChunker` or `PdfChunker` would have its own idea of what
    metadata looks like and no use for a YAML dict.
    """

    path: str
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    """A passage, and enough about where it came from to cite it.

    The single most important thing here is that `text` carries a breadcrumb
    line before the body:

        Returns and Refunds Policy (POL-RET-001 v4.2) > 2. Category exceptions

        | Opened audio | 14 days | Hygiene restriction... |

    That one line does three jobs at once. It makes an orphaned table row
    findable -- a row about "14 days" with no header above it is unattributable
    prose otherwise. It re-attaches the front matter, which is invisible to a
    similarity search if kept purely as metadata. And it survives into the
    prompt, so the model can cite a document and a section instead of asserting
    a policy from nowhere.

    One field rather than separate embed/display/cite texts, because three
    fields is three chances for them to drift apart, and the same string turns
    out to be right for all three jobs.

    Two fields for where it sits, because they answer different questions.
    `section` is the citation label -- short, stable, the thing an answer
    quotes ("§2"). `heading` is the full readable path ("2. Category
    exceptions", or "1. Headphones > Pebble Drift ANC") and is what goes in the
    breadcrumb. Deriving one from the other at the point of use would mean
    every caller re-doing the same string surgery.
    """

    id: str
    text: str
    doc_id: str
    title: str
    version: str
    section: str
    heading: str
    ordinal: int
    source: str
    effective_from: date | None = None

    @property
    def citation(self) -> str:
        """How this passage refers to itself in an answer."""
        return f"{self.doc_id} v{self.version} §{self.section}"


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """A chunk and its embedding, on the way into a store."""

    chunk: Chunk
    vector: Vector


@dataclass(frozen=True, slots=True)
class Hit:
    """A chunk the search turned up, and how well it matched.

    `score` is higher-is-better and comparable only within one search. Cosine
    similarity today; a reranker replaces the number with its own and the
    ordering still means the same thing.
    """

    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class IndexManifest:
    """What an index was built from.

    This exists because of one specific failure. Re-index with a different
    embedding model at the same dimension count and everything still works:
    vectors go in, neighbours come out, no error anywhere. The answers are just
    quietly wrong, because the query is being compared against points from a
    different space. There is nothing to notice and nothing to debug.

    So the index records what made it, and the app refuses to serve one it
    cannot match. This is the difference between the pieces being replaceable
    in principle and being replaceable safely.
    """

    model_id: str
    dimensions: int
    chunker: str
    chunk_count: int
    built_at: str


class IndexMismatchError(RuntimeError):
    """The index on disk was not built by the embedder that is now running."""


class Chunker(Protocol):
    """Cuts a document into passages. Any class with this method works."""

    @property
    def name(self) -> str:
        """Identifies this chunker in an `IndexManifest`."""
        ...

    def split(self, document: Document) -> Sequence[Chunk]:
        """Return the chunks of `document`, in the order they appear in it.

        Synchronous, unlike every other port here, because chunking is pure
        string work. Nothing is gained by making callers await it.
        """
        ...


class Embedder(Protocol):
    """Turns text into vectors. Any class with these members works."""

    @property
    def model_id(self) -> str:
        """Which model these vectors come from, e.g. `openai:text-embedding-3-small`.

        Goes into the manifest, and is the whole basis of the staleness check.
        Two embedders with the same dimension count and different ids produce
        vectors that must never be compared, and this string is the only thing
        that can tell them apart.

        Note there is deliberately no `dimensions` here. It would be a second
        copy of a fact the vectors themselves already carry, declared before
        anything has been embedded and therefore able to be wrong. The indexer
        reads the real length off the first batch instead.
        """
        ...

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed passages for storage. Returns one vector per input, in order.

        Batched on purpose: providers charge and rate-limit per request, and
        embedding a corpus one string at a time is the slowest possible way to
        do it.
        """
        ...

    async def embed_query(self, text: str) -> Vector:
        """Embed a question for search.

        Separate from `embed_documents` for the asymmetry described at the top
        of this file, not because the batching differs.
        """
        ...


class VectorStore(Protocol):
    """Nearest-neighbour search over vectors. Any class with these works."""

    async def describe(self) -> IndexManifest | None:
        """What is in the index, or `None` if nothing has been written yet.

        `None` is the fresh-checkout case, and it is a different answer from a
        manifest that disagrees with the running embedder: the first means
        "run the indexer", the second means "your index is stale".
        """
        ...

    async def write(
        self, manifest: IndexManifest, records: Sequence[VectorRecord]
    ) -> None:
        """Replace the entire index with `records`, described by `manifest`.

        Replace, not append, and both together. Two reasons.

        Appending -- or upserting on a stable id -- leaves orphans. Delete a
        section from a policy document and its chunk stays in the index
        forever, quietly retrievable, citing a rule that no longer exists.
        Nothing ever notices, because the failure is a chunk that is *present*.

        And writing the manifest in the same call means an index can never be
        separated from the record of what built it. A separate `set_manifest`
        would eventually be forgotten in some path, which puts you back to
        vectors of unknown provenance.

        The cost is that the whole corpus must fit in one call. At this size
        that is not a constraint; at a size where it is, this port grows a
        batching story and the adapters below it change.
        """
        ...

    async def search(self, vector: Vector, k: int) -> Sequence[Hit]:
        """Return up to `k` nearest chunks to `vector`, best first.

        No filter argument yet. Metadata filtering -- by `doc_id`, or by
        `effective_from` to answer as of a date -- is the obvious next thing
        this port grows, and it is left out until something asks for it rather
        than guessed at now.
        """
        ...


@runtime_checkable
class SupportsPersistence(Protocol):
    """Optional: a store that has to be told to write itself to disk.

    Kept off `VectorStore` deliberately, exactly as `SupportsTokenChoices` is
    kept off `ChatModel` in `sage.domain.llm`. A server-backed store persists
    on write and has nothing to do here; forcing it to implement an empty
    `persist` is how a small port turns into a big one.

    The indexing pipeline checks `isinstance(store, SupportsPersistence)` and
    calls this if it is there. That check works because of `@runtime_checkable`.
    """

    async def persist(self) -> None:
        """Flush the index to wherever it lives between runs."""
        ...


class Retriever(Protocol):
    """Finds the passages worth putting in front of the model.

    Takes the whole `Conversation`, not just the question string, and that is
    the point of the signature. Turn three of a real conversation is "can I
    return them?" -- no noun, no product, and an embedding of it retrieves
    nothing useful. Fixing that means rewriting the query against the history
    before embedding it, which is a second model call and lives *here*, in a
    new `Retriever`, not in the store and not in the context strategy.

    That is not built yet. Passing the conversation now means it can be, later,
    without this file or anything above it moving.
    """

    async def retrieve(self, conversation: Conversation) -> Sequence[Hit]:
        """Return the passages for this conversation, best first.

        May return nothing. Once a score threshold lands, "nothing matched well
        enough" becomes the honest answer to a question the corpus does not
        cover, and the caller has to be able to say so.
        """
        ...
