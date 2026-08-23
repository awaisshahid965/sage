"""The conversation store port.

Where a conversation lives between requests. The third seam, beside
`sage.domain.llm` (who answers) and `sage.domain.context` (what they are told):
this one is *what is remembered*.

Two things about the shape are load-bearing:

**A missing conversation is not an empty one.** `load` returns `None` for an id
nothing points at, and `[]` for a real conversation with no turns yet. The
caller needs to tell those apart, because the first means "mint a new id" and
the second means "carry on". Collapsing them would silently resurrect expired
ids and let a client keep an id alive forever by guessing.

**The store, not the caller, owns expiry.** `append` refreshes the lifetime of
whatever it writes to, so a conversation expires after a period of *silence*
rather than a fixed period after it started. Someone mid-conversation never
loses it out from under them; someone who wandered off a day ago does.
"""

from collections.abc import Sequence
from typing import Protocol

from sage.domain.llm import Message


class ConversationStore(Protocol):
    """Somewhere conversations are kept. Any class with these methods works."""

    async def load(self, conversation_id: str) -> list[Message] | None:
        """Return the turns for `conversation_id`, oldest first.

        `None` means no conversation is stored under that id — it expired, was
        evicted, or never existed. The three are indistinguishable here and
        that is fine: the answer is the same in all of them.
        """
        ...

    async def append(self, conversation_id: str, turns: Sequence[Message]) -> None:
        """Add `turns` to a conversation, creating it if it is not there.

        Also refreshes its expiry. Called once per completed exchange with both
        halves of it, rather than once per turn, so a failed reply cannot leave
        a question stored with nothing answering it.
        """
        ...
