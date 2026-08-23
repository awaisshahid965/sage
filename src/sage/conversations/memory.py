"""A conversation store that lives in the process, with no Redis behind it.

The `echo` of this port. Tests and CI exercise the real endpoints, the real
service and the real expiry rules without a container, and the app boots with
no infrastructure at all.

Single-process only, and everything is lost on restart — which is exactly why
it is not the default outside tests.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sage.config import Settings
from sage.domain.conversation import ConversationStore
from sage.domain.llm import Message

# Monotonic seconds. Injectable so a test can age a conversation past its TTL
# without sleeping through it.
Clock = Callable[[], float]


@dataclass(slots=True)
class _Entry:
    turns: list[Message]
    expires_at: float


class InMemoryConversationStore:
    """Conversations in a dict, with expiry checked on read.

    Expiry is lazy: nothing sweeps the dict on a timer, an entry is simply
    treated as absent once its deadline has passed. For a store whose whole
    lifetime is one process that is enough, and it keeps the semantics
    identical to Redis, which also expires keys without the caller noticing.
    """

    def __init__(self, ttl_seconds: int, clock: Clock = time.monotonic) -> None:
        self._entries: dict[str, _Entry] = {}
        self._ttl = ttl_seconds
        self._now = clock

    async def load(self, conversation_id: str) -> list[Message] | None:
        entry = self._entries.get(conversation_id)
        if entry is None:
            return None

        if entry.expires_at <= self._now():
            # Drop it now rather than leaving it to be rediscovered later.
            del self._entries[conversation_id]
            return None

        return list(entry.turns)

    async def append(self, conversation_id: str, turns: Sequence[Message]) -> None:
        entry = self._entries.get(conversation_id)

        if entry is None or entry.expires_at <= self._now():
            entry = _Entry(turns=[], expires_at=0.0)
            self._entries[conversation_id] = entry

        entry.turns.extend(turns)
        # Sliding, not fixed: the clock restarts on every write, so expiry
        # measures silence rather than age.
        entry.expires_at = self._now() + self._ttl


def build(settings: Settings) -> ConversationStore:
    """Build the in-memory store. Takes settings so every builder looks alike."""
    return InMemoryConversationStore(ttl_seconds=settings.conversation_ttl_seconds)
