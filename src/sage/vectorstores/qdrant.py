"""Approximate nearest-neighbour search, in Qdrant.

Qdrant builds an HNSW graph over the vectors -- a navigable small-world
structure where a search walks from an entry point towards the query instead of
scoring every point. That trades exactness for time: the walk can miss a true
neighbour, and the miss rate is what `poe bench` measures against
`BruteForceStore`.

At this corpus's size that trade is a loss, and the code says so rather than
pretending otherwise. A few hundred vectors is a matrix multiply that finishes
before the HTTP request to Qdrant is serialised. What this adapter buys is the
shape of the thing at a size where it matters, and the measurement that shows
where that size begins.

**Local mode is the reason the tests stay offline.** `AsyncQdrantClient` takes
`location=":memory:"` or `path=...` and runs the same API with no server, so
the whole retrieval path can be exercised in CI without a container. The
compose service is for `poe up`, not for `poe check`.

**Two reasons this may not be approximate at all**, and both are worth knowing
before quoting a recall number at anyone.

The first is local mode. `QdrantLocal` scores the query against every vector
with numpy -- read `local_collection.search`, it is a `calculate_distance` over
the whole array. It builds no graph. It reports an `hnsw_config` when asked,
because that is part of the collection schema it is imitating, and that config
does nothing. So an index served from `:memory:` or a path is *exact*, and a
benchmark comparing it against `BruteForceStore` would report perfect recall
while measuring two brute-force searches against each other.

The second catches the server too. Qdrant's `full_scan_threshold` -- 10 MB of
vectors by default -- makes small collections skip the graph, on the entirely
correct grounds that scanning them is faster. This corpus is 82 chunks: about
170 KB at 512 dimensions, two orders of magnitude under the threshold. A real
server would also answer it exactly.

Neither is a bug, and both mean the same thing: at this size nothing here is
approximate, whatever the stack diagram says. `full_scan_threshold` is
therefore exposed rather than left at its default, so the choice to force the
graph is one somebody made on purpose -- and `poe bench` is what says at which
corpus size making it starts to pay.

**The manifest lives in a sidecar collection.** Two other places were possible
and both are worse. A reserved point inside the main collection needs a fake
vector sitting in the semantic space and a `must_not` filter on every single
query, which is a correctness bug the first time someone writes a query that
forgets it. Collection config has nowhere to put arbitrary fields. So there is
a second, one-dimensional collection holding a single point.

It is written *last*, deliberately. A crash part-way through indexing then
leaves vectors with no manifest, which `describe()` reports as no index at all,
which asks for a rebuild. The opposite order would leave a manifest vouching
for a half-written index -- and a half-written index is the failure that says
nothing and answers wrongly.
"""

from collections.abc import Iterator, Sequence
from dataclasses import asdict
from datetime import date
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client import AsyncQdrantClient, models

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

# Points per upsert. Large enough that a corpus goes up in a handful of round
# trips, small enough that one request body stays a sane size.
BATCH = 256

MANIFEST_SUFFIX = "_manifest"
MANIFEST_POINT_ID = 0

_POINT_NAMESPACE = uuid5(NAMESPACE_URL, "https://sage.invalid/qdrant-point")


class QdrantStore:
    """A `VectorStore` backed by a Qdrant collection."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection: str,
        full_scan_threshold: int | None = None,
    ) -> None:
        """`full_scan_threshold` is in kilobytes of vector data; below it,
        Qdrant ignores the graph and scans. `0` forces the graph always, which
        is what a benchmark wants and what a small production collection
        emphatically does not. `None` leaves Qdrant's own default alone."""
        self._client = client
        self._collection = collection
        self._full_scan_threshold = full_scan_threshold
        self._manifest_collection = f"{collection}{MANIFEST_SUFFIX}"

    async def describe(self) -> IndexManifest | None:
        if not await self._client.collection_exists(self._manifest_collection):
            return None

        points = await self._client.retrieve(
            collection_name=self._manifest_collection,
            ids=[MANIFEST_POINT_ID],
            with_payload=True,
        )
        if not points or points[0].payload is None:
            return None

        return IndexManifest(**points[0].payload)

    async def write(
        self, manifest: IndexManifest, records: Sequence[VectorRecord]
    ) -> None:
        # Drop the manifest before touching the vectors. From here until the
        # last line of this method, `describe()` says "no index" -- which is
        # true, and is what a reader mid-write should be told.
        await self._drop(self._manifest_collection)
        await self._drop(self._collection)

        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(
                size=manifest.dimensions,
                # Cosine, so Qdrant normalises on insert and the score comes
                # back as a similarity in [-1, 1] -- the same number the
                # brute-force store reports, which is what makes the two
                # comparable in a benchmark at all.
                distance=models.Distance.COSINE,
            ),
            hnsw_config=(
                None
                if self._full_scan_threshold is None
                else models.HnswConfigDiff(
                    full_scan_threshold=self._full_scan_threshold
                )
            ),
        )

        for batch in _batched(records, BATCH):
            await self._client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=_point_id(record.chunk.id),
                        vector=list(record.vector),
                        payload=_payload(record.chunk),
                    )
                    for record in batch
                ],
            )

        await self._client.create_collection(
            collection_name=self._manifest_collection,
            # One dimension, never searched. Qdrant requires a vector config;
            # this is the smallest legal answer to that requirement.
            vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT),
        )
        await self._client.upsert(
            collection_name=self._manifest_collection,
            points=[
                models.PointStruct(
                    id=MANIFEST_POINT_ID, vector=[1.0], payload=asdict(manifest)
                )
            ],
        )

        log.info(
            "index_written",
            collection=self._collection,
            chunks=len(records),
            dimensions=manifest.dimensions,
        )

    async def search(self, vector: Vector, k: int) -> Sequence[Hit]:
        if k <= 0 or not await self._client.collection_exists(self._collection):
            return []

        response = await self._client.query_points(
            collection_name=self._collection,
            query=list(vector),
            limit=k,
            with_payload=True,
        )

        return [
            Hit(chunk=_chunk(point.payload), score=point.score)
            for point in response.points
            if point.payload is not None
        ]

    async def _drop(self, collection: str) -> None:
        if await self._client.collection_exists(collection):
            await self._client.delete_collection(collection)


def _point_id(chunk_id: str) -> str:
    """A Qdrant-legal id for a chunk, whatever the chunker chose to call it.

    Qdrant accepts only UUIDs and unsigned integers as point ids. Nothing in
    `Chunk` says so, and nothing should: a chunker that used readable ids like
    `POL-RET-001#2` would work perfectly against `BruteForceStore` and fail
    here, which is a constraint from one backend imposed on every other
    implementation of the port.

    So it is absorbed. Ids that are already UUIDs pass through unchanged --
    which is every id `HeadingChunker` produces -- and anything else is hashed
    into one, deterministically, so the mapping is the same on every run. The
    chunk's real id travels in the payload and is what callers get back, so the
    translation is invisible above this file.
    """
    try:
        return str(UUID(chunk_id))
    except ValueError:
        return str(uuid5(_POINT_NAMESPACE, chunk_id))


def _payload(chunk: Chunk) -> dict[str, Any]:
    """A chunk as Qdrant payload.

    The whole chunk goes in, not just an id pointing at a row somewhere else.
    A store that returns ids forces every caller to hold a second lookup table
    and keep it in step with the index -- two things to rebuild, one of which
    will eventually be forgotten.
    """
    fields = asdict(chunk)
    effective_from = fields["effective_from"]
    fields["effective_from"] = effective_from.isoformat() if effective_from else None
    return fields


def _chunk(payload: dict[str, Any]) -> Chunk:
    fields = dict(payload)
    effective_from = fields.pop("effective_from", None)
    return Chunk(
        **fields,
        effective_from=date.fromisoformat(effective_from) if effective_from else None,
    )


def _batched(
    records: Sequence[VectorRecord], size: int
) -> Iterator[Sequence[VectorRecord]]:
    for start in range(0, len(records), size):
        yield records[start : start + size]


def build(settings: Settings) -> VectorStore:
    """Build a Qdrant-backed store.

    `SAGE_QDRANT_URL=:memory:` and `SAGE_QDRANT_URL=./some/path` both select
    local mode, where the client runs the engine in-process. Anything else is
    treated as a server URL.
    """
    url = settings.qdrant_url

    if url == ":memory:":
        client = AsyncQdrantClient(location=":memory:")
    elif not url.startswith(("http://", "https://")):
        client = AsyncQdrantClient(path=url)
    else:
        client = AsyncQdrantClient(url=url)

    return QdrantStore(
        client,
        settings.qdrant_collection,
        full_scan_threshold=settings.qdrant_full_scan_threshold,
    )


def is_exact(url: str) -> bool:
    """Whether a store at `url` will answer exactly regardless of its config.

    Local mode has no graph to be approximate with. `poe bench` asks this
    before reporting a recall figure, because "100% of the exact results
    recovered" is a true and completely worthless sentence when both sides of
    the comparison are doing the same exact scan.
    """
    return not url.startswith(("http://", "https://"))
