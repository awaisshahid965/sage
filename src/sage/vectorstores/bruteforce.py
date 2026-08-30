"""Exact nearest-neighbour search, by comparing against everything.

This is not a placeholder for the real store, and it is not here because ANN
was too much work. It is the **oracle**: the definition of the right answer,
against which an approximate index is measured. `poe bench` asks both stores
the same questions and reports how much of the exact top-k the approximate one
recovered. Without this class that number cannot be computed, and "we use HNSW"
is a claim with nothing behind it.

It is also, at this corpus size, *faster* than the alternative. A few hundred
chunks is one small matrix multiply -- tens of microseconds, with no graph to
traverse and no index to build. Approximate search wins somewhere north of tens
of thousands of vectors, and pretending otherwise for a corpus of eight policy
documents would be theatre. The benchmark exists to find where that crossover
actually is rather than to assert it.

Same argument as `FullHistory` in `sage.context.history`: the honest baseline,
kept because every later technique is a claim measured against it.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from sage.config import Settings
from sage.domain.retrieval import (
    Chunk,
    Hit,
    IndexManifest,
    Vector,
    VectorRecord,
    VectorStore,
)
from sage.logging import get_logger

log = get_logger(__name__)

MANIFEST_FILE = "manifest.json"
CHUNKS_FILE = "chunks.json"
VECTORS_FILE = "vectors.npy"

# float32, not 64. Halves the file and the memory for a similarity that is only
# ever compared against its neighbours -- the seventh decimal place has never
# changed a ranking.
_DTYPE = np.float32


class BruteForceStore:
    """Every vector in one matrix; search is one multiply and a sort."""

    def __init__(self, path: Path | None = None) -> None:
        """`path` is where the index lives between runs. `None` keeps it in
        memory only, which is what tests and `:memory:`-style use want."""
        self._path = path
        self._manifest: IndexManifest | None = None
        self._chunks: list[Chunk] = []
        self._matrix: NDArray[np.float32] = np.zeros((0, 0), dtype=_DTYPE)

    async def describe(self) -> IndexManifest | None:
        return self._manifest

    async def write(
        self, manifest: IndexManifest, records: Sequence[VectorRecord]
    ) -> None:
        self._manifest = manifest
        self._chunks = [record.chunk for record in records]
        self._matrix = _unit_rows(
            np.array([record.vector for record in records], dtype=_DTYPE)
        )

    async def search(self, vector: Vector, k: int) -> Sequence[Hit]:
        if not self._chunks or k <= 0:
            return []

        query = _unit_rows(np.array([vector], dtype=_DTYPE))[0]

        # Rows are unit length and so is the query, so the dot product *is*
        # cosine similarity. Doing the normalising once at write time turns
        # every future search into a single matrix-vector multiply.
        scores = self._matrix @ query

        # argpartition finds the top k without sorting the other n-k, which is
        # the whole point of not calling argsort on the full array. The k it
        # returns are unordered, so they get sorted afterwards -- k elements,
        # not n.
        k = min(k, len(self._chunks))
        top = np.argpartition(-scores, k - 1)[:k]
        ranked = top[np.argsort(-scores[top])]

        return [Hit(chunk=self._chunks[i], score=float(scores[i])) for i in ranked]

    async def persist(self) -> None:
        """Write the index to `path`. Satisfies `SupportsPersistence`."""
        if self._path is None:
            return
        if self._manifest is None:
            raise RuntimeError("Nothing to persist: no index has been written.")

        self._path.mkdir(parents=True, exist_ok=True)

        # Three files rather than one pickle. A pickle of application objects
        # cannot be read once those classes move, is unreadable by anything
        # that is not this program, and executes arbitrary code on load. The
        # manifest and chunks stay diffable text; only the matrix is binary,
        # because it genuinely is.
        (self._path / MANIFEST_FILE).write_text(
            json.dumps(asdict(self._manifest), indent=2), encoding="utf-8"
        )
        (self._path / CHUNKS_FILE).write_text(
            json.dumps([_chunk_to_json(c) for c in self._chunks], indent=2),
            encoding="utf-8",
        )
        np.save(self._path / VECTORS_FILE, self._matrix)

        log.info(
            "index_persisted",
            path=str(self._path),
            chunks=len(self._chunks),
            dimensions=self._manifest.dimensions,
        )

    def load(self) -> None:
        """Read the index back from `path`, if one is there.

        Silent when there is nothing to load. A fresh checkout has no index and
        that is not an error -- `describe()` returning `None` is how the app
        finds out, and it can say "run the indexer" rather than crash.
        """
        if self._path is None or not (self._path / MANIFEST_FILE).exists():
            return

        manifest = json.loads((self._path / MANIFEST_FILE).read_text(encoding="utf-8"))
        chunks = json.loads((self._path / CHUNKS_FILE).read_text(encoding="utf-8"))

        self._manifest = IndexManifest(**manifest)
        self._chunks = [_chunk_from_json(c) for c in chunks]
        self._matrix = np.load(self._path / VECTORS_FILE).astype(_DTYPE)

        log.info("index_loaded", path=str(self._path), chunks=len(self._chunks))


def _unit_rows(matrix: NDArray[np.float32]) -> NDArray[np.float32]:
    """Scale every row to length 1, leaving all-zero rows alone.

    An empty corpus arrives here as a (0, 0) array, and a text with nothing
    recognisable in it as a row of zeros. Neither should raise, and neither
    should become NaN -- a NaN row poisons every later comparison silently,
    which is far worse than a row that simply matches nothing.
    """
    if matrix.size == 0:
        return matrix

    lengths = np.linalg.norm(matrix, axis=1, keepdims=True)
    # `.astype` because numpy widens float32 to float64 on division, and the
    # whole array would silently double in size on every write.
    return (matrix / np.where(lengths == 0, 1, lengths)).astype(_DTYPE, copy=False)


def _chunk_to_json(chunk: Chunk) -> dict[str, Any]:
    fields = asdict(chunk)
    effective_from = fields["effective_from"]
    fields["effective_from"] = effective_from.isoformat() if effective_from else None
    return fields


def _chunk_from_json(fields: dict[str, Any]) -> Chunk:
    effective_from = fields.pop("effective_from", None)
    return Chunk(
        **fields,
        effective_from=date.fromisoformat(effective_from) if effective_from else None,
    )


def build(settings: Settings) -> VectorStore:
    """Build the brute-force store, loading any index already on disk.

    Loading here rather than on first search means a stale or missing index is
    discovered at startup, next to the manifest check, instead of in the middle
    of answering someone.
    """
    store = BruteForceStore(path=settings.index_path)
    store.load()
    return store
