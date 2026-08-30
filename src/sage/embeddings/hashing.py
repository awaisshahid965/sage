"""An embedder that needs no network and no API key.

The `echo` of this port, with one difference worth understanding.

`EchoChatModel` only has to prove the seam is real. A fake embedder could do
the same by returning random vectors -- but then no test above it could assert
anything useful, because "the returns policy came back for a question about
returns" would be pure chance. The retrieval pipeline would be exercised and
never actually checked.

So this is a real embedder, just a weak one: the hashing trick, which is
bag-of-words with the vocabulary replaced by a hash function. Each word is
hashed into a bucket and adds to that dimension. Two texts sharing words end up
pointing in similar directions, so cosine similarity over these vectors is
genuine lexical overlap.

That is enough to make the whole retrieval path testable offline and for free
-- chunker, store, retriever and context strategy, end to end, with real
assertions about which passage came back.

Two things it cannot do, both worth knowing before writing a test against it.

**No semantics.** "Can I send this back?" and "returns policy" share no words,
so this scores them at zero. It is a keyword search wearing a vector's clothes.

**No IDF, so common words dominate.** Every word counts the same, which means
"How long do I have to return something?" is mostly *how, long, do, I, have,
to* -- six ubiquitous words against one useful one -- and the nearest passage
is whichever chunk happens to be richest in stopwords. Real lexical search
solves this by weighting a term against how rare it is in the corpus, and that
is not available here: `Embedder` embeds one text at a time with no view of the
corpus, and it has to, because a query is embedded when the corpus is nowhere
in sight. Statelessness is the right shape for the port and it rules out IDF,
which is a large part of why production systems reach for a learned embedding
model rather than this.

The practical consequence is that tests against this embedder should use
keyword-shaped queries -- "restocking fee", "PebbleCare+ extended cover" --
rather than natural questions. Those exercise every piece of the pipeline
honestly. Whether natural questions find the right passage is a question about
a real embedding model, and it belongs to the eval work, not to the unit suite.
"""

import hashlib
import math
import re
from collections.abc import Sequence

from sage.config import Settings
from sage.domain.retrieval import Embedder, Vector

_WORD = re.compile(r"[a-z0-9]+")

# Enough buckets that collisions between the corpus's few thousand distinct
# words are rare, and small enough to stay cheap.
DEFAULT_DIMENSIONS = 512


class HashingEmbedder:
    """Bag-of-words into a fixed number of buckets, L2-normalised."""

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        # Versioned, because changing the tokeniser or the hash changes the
        # space these vectors live in. An index built by v1 must not be served
        # by v2, and the manifest check can only catch that if the id moves.
        return f"hashing:v1:{self._dimensions}"

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> Vector:
        # Symmetric: the same text embeds the same way whichever side it is on.
        # A model with `passage:`/`query:` prefixes is where these two diverge.
        return self._embed(text)

    def _embed(self, text: str) -> Vector:
        vector = [0.0] * self._dimensions

        for word in _WORD.findall(text.lower()):
            # blake2b, not the built-in `hash`. Python randomises string
            # hashing per process unless PYTHONHASHSEED is pinned, so `hash`
            # here would produce an index that cannot be read back by the
            # process that comes after it -- and the failure would look like
            # bad retrieval rather than like a bug.
            digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
            code = int.from_bytes(digest, "big")

            # One bit spent on a sign, so that colliding words are as likely to
            # cancel as to reinforce. Without it every collision inflates the
            # bucket and common words drag unrelated texts together.
            bucket = (code >> 1) % self._dimensions
            vector[bucket] += 1.0 if code & 1 else -1.0

        return _normalise(vector)


def _normalise(vector: list[float]) -> list[float]:
    """Scale to unit length, so cosine similarity is a plain dot product.

    A text with no recognisable words comes back as all zeros rather than as a
    division by zero. It matches nothing, which is the correct answer.
    """
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0.0:
        return vector
    return [value / length for value in vector]


def build(settings: Settings) -> Embedder:
    """Build the hashing embedder. Takes settings so every builder looks alike."""
    del settings
    return HashingEmbedder()
