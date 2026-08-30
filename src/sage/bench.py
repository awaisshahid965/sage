"""What the approximation costs, measured rather than assumed.

    uv run poe bench              # the corpus at its real size
    uv run poe bench 50000        # padded, to find where HNSW starts to pay

Exact and approximate search go behind the same port precisely so that this
comparison is possible: the same vectors, the same questions, two stores, and a
number for the difference. Without it, "we use HNSW" is a stack decoration.

**What this measures and what it does not.** It reports agreement between the
two stores -- how much of the exact top-k the approximate one recovered -- and
how long each took. It says nothing about whether those passages answer the
question. That is answer quality, it needs the ground truth in
`eval-questions.md`, and it is a separate piece of work. Conflating them is how
a retrieval system ends up with a good-looking number that measures the wrong
thing.

**Why the padding exists.** At 82 chunks there is nothing to measure. Qdrant
skips its graph below `full_scan_threshold`, so both stores scan exhaustively
and recall is 100% by construction. Padding to tens of thousands of vectors is
what puts the graph in play, and the padding is synthetic: real chunk vectors
with gaussian noise added, so the space stays clustered the way embeddings are,
rather than uniform noise where every point is equidistant and ANN looks
better than it is. Synthetic is still synthetic, and the number is a guide to
the shape of the curve, not a production SLO.
"""

import asyncio
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from sage.chunking.markdown import HeadingChunker
from sage.config import Settings, get_settings
from sage.domain.retrieval import (
    Chunk,
    Embedder,
    IndexManifest,
    VectorRecord,
    VectorStore,
)
from sage.embeddings.factory import create_embedder
from sage.indexing.corpus import load_documents
from sage.logging import configure_logging
from sage.vectorstores.bruteforce import BruteForceStore
from sage.vectorstores.qdrant import build, is_exact

TOP_K = 5

# How far a synthetic vector is pushed away from the real one it was cloned
# from. Small enough that the clusters stay clusters.
NOISE = 0.35

# Repeats per query, so a single scheduling hiccup does not become the
# headline number.
ROUNDS = 3


@dataclass(frozen=True, slots=True)
class Timing:
    recall: float
    median_ms: float
    total: int


async def _corpus_records(settings: Settings) -> tuple[list[Chunk], list[list[float]]]:
    chunker = HeadingChunker(max_chars=settings.chunk_max_chars)
    embedder = create_embedder(settings)

    chunks: list[Chunk] = []
    for document in load_documents(settings.corpus_path):
        chunks.extend(chunker.split(document))

    vectors = await embedder.embed_documents([chunk.text for chunk in chunks])
    return chunks, [list(vector) for vector in vectors]


def _pad(
    chunks: Sequence[Chunk], vectors: Sequence[list[float]], target: int
) -> list[VectorRecord]:
    """Grow the record set to `target` with plausible neighbours of real ones."""
    records = [
        VectorRecord(chunk=chunk, vector=vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    if target <= len(records):
        return records

    # Seeded, so two runs of the bench compare the same index rather than two
    # different random ones.
    rng = np.random.default_rng(0)
    source = np.array(vectors, dtype=np.float32)

    for index in range(target - len(records)):
        original = source[rng.integers(len(source))]
        noisy = original + rng.normal(0, NOISE, size=original.shape).astype(np.float32)
        noisy /= np.linalg.norm(noisy) or 1.0

        # Synthetic chunks are labelled as such. A padded index that cannot be
        # told apart from a real one is an index somebody will eventually serve
        # to a customer.
        records.append(
            VectorRecord(
                chunk=Chunk(
                    id=f"synthetic-{index}",
                    text="synthetic padding",
                    doc_id="SYNTHETIC",
                    title="synthetic",
                    version="0",
                    section="0",
                    heading="synthetic",
                    ordinal=index,
                    source="synthetic",
                ),
                vector=[float(value) for value in noisy],
            )
        )

    return records


def _questions(settings: Settings) -> list[str]:
    """The questions from `eval-questions.md`, used here only as realistic input.

    The file is excluded from the index for good reason (see
    `sage.indexing.corpus`), but reading it for query *text* is fine: this
    benchmark never looks at the expected answers, only at whether two stores
    agree about which passages are nearest.
    """
    path = settings.corpus_path / "eval-questions.md"
    questions: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        # A data row is `| id | question | ... |`, so five cells at minimum
        # once the empty edges are counted. The separator row is all dashes.
        if len(cells) >= 5 and cells[1] and not set(cells[1]) <= {"-", "#"}:
            if cells[1].lower() in {"#", "id"}:
                continue
            questions.append(cells[2])

    return questions


async def _measure(
    store: VectorStore,
    queries: Sequence[list[float]],
    exact: Sequence[Sequence[str]] | None,
) -> Timing:
    latencies: list[float] = []
    recovered = 0.0

    for index, query in enumerate(queries):
        for round_ in range(ROUNDS):
            start = time.perf_counter()
            hits = await store.search(query, TOP_K)
            latencies.append((time.perf_counter() - start) * 1000)

            if round_ == 0 and exact is not None:
                found = {hit.chunk.id for hit in hits}
                recovered += len(found & set(exact[index])) / max(len(exact[index]), 1)

    return Timing(
        recall=recovered / len(queries) if queries and exact is not None else 1.0,
        median_ms=float(np.median(latencies)),
        total=len(queries) * ROUNDS,
    )


def render(
    size: int,
    questions: int,
    exact_timing: Timing,
    ann_timing: Timing,
    ann_is_exact: bool,
) -> str:
    lines = [
        "",
        f"  vectors    : {size:,}",
        f"  queries    : {questions} x {ROUNDS} rounds, top-{TOP_K}",
        "",
        f"  bruteforce : {exact_timing.median_ms:7.3f} ms median   (exact, the oracle)",
        f"  qdrant     : {ann_timing.median_ms:7.3f} ms median",
        "",
    ]

    if ann_is_exact:
        lines += [
            "  recall     : not reported.",
            "",
            "  Qdrant is in local mode here, which scans every vector in numpy and",
            "  builds no graph. Both columns above are exact search, so a recall",
            "  figure would read 100% and mean nothing. Point SAGE_QDRANT_URL at a",
            "  server (`docker compose up qdrant`) and set",
            "  SAGE_QDRANT_FULL_SCAN_THRESHOLD=0 to measure the real thing.",
            "",
        ]
    else:
        lines += [
            f"  recall@{TOP_K}   : {ann_timing.recall:6.1%} of the exact top-{TOP_K} recovered",
            "",
        ]

    return "\n".join(lines)


async def run(target: int) -> int:
    settings = get_settings()
    configure_logging(level="WARNING", json_output=False)

    embedder: Embedder = create_embedder(settings)

    chunks, vectors = await _corpus_records(settings)
    records = _pad(chunks, vectors, target)

    manifest = IndexManifest(
        model_id=embedder.model_id,
        dimensions=len(vectors[0]),
        chunker="bench",
        chunk_count=len(records),
        built_at="bench",
    )

    exact_store = BruteForceStore()
    await exact_store.write(manifest, records)

    ann_store = build(settings)
    await ann_store.write(manifest, records)

    questions = _questions(settings)
    queries = [list(await embedder.embed_query(question)) for question in questions]

    # The oracle runs first, and its answers become the target the approximate
    # store is scored against. That ordering is the whole point of keeping an
    # exact implementation around.
    exact_hits: list[list[str]] = []
    for query in queries:
        hits = await exact_store.search(query, TOP_K)
        exact_hits.append([hit.chunk.id for hit in hits])

    exact_timing = await _measure(exact_store, queries, None)
    ann_timing = await _measure(ann_store, queries, exact_hits)

    print(
        render(
            len(records),
            len(questions),
            exact_timing,
            ann_timing,
            is_exact(settings.qdrant_url),
        )
    )
    return 0


def main() -> None:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sys.exit(asyncio.run(run(target)))


if __name__ == "__main__":
    main()
