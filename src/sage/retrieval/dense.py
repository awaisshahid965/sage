"""Retrieval by vector similarity alone.

Embed the question, ask the store for its nearest neighbours, hand them back.
That is the whole technique, and naming it "dense" rather than "the retriever"
is the point: the sibling classes that will sit beside it -- hybrid dense +
BM25, or a reranker wrapping either -- are not variations on this one.

This class is small on purpose. Everything it does *not* do is something with
its own reason to change, and each of those is a change here and nowhere else:

- **Query rewriting.** "Can I return them?" on turn three has no noun in it and
  embeds to nothing useful. Rewriting it against the history costs a model call
  and belongs in this file, which is why `retrieve` takes the whole
  `Conversation` and not a string. Deferred until the current stage lands.
- **A score threshold.** Right now the k nearest passages come back whether or
  not any of them is relevant, because "nothing matched" needs a number and
  that number has to be chosen against an eval set rather than guessed. Once it
  exists, this returns an empty sequence and `Passages` selects nothing.
"""

from collections.abc import Sequence

from sage.domain.context import Conversation
from sage.domain.retrieval import Embedder, Hit, VectorStore


class DenseRetriever:
    """Nearest neighbours of the embedded question."""

    def __init__(self, embedder: Embedder, store: VectorStore, top_k: int) -> None:
        self._embedder = embedder
        self._store = store
        self._top_k = top_k

    async def retrieve(self, conversation: Conversation) -> Sequence[Hit]:
        # `embed_query`, not `embed_documents`. Identical for the models in use
        # here and emphatically not for others — see `sage.domain.retrieval`.
        vector = await self._embedder.embed_query(conversation.question)

        return await self._store.search(vector, self._top_k)
