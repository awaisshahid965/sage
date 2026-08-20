"""Context drawn from the conversation itself.

One strategy today. A sliding window and a summarising strategy belong here
too when they arrive -- each a new class beside this one, not an edit to it.
"""

from collections.abc import Sequence

from sage.domain.context import Conversation
from sage.domain.llm import Message


class FullHistory:
    """Sends every turn there has ever been.

    The honest starting point and the wrong long-term answer, both on purpose.
    The prompt grows without bound, so cost and latency climb with the length
    of the conversation until a request is refused for overflowing the context
    window -- and because providers bill per input token, every turn re-pays
    for all the turns before it.

    It is here because it is the behaviour to beat. Every later strategy is a
    claim that something can be dropped without the answers getting worse, and
    this is what that claim gets measured against.
    """

    async def select(self, conversation: Conversation) -> Sequence[Message]:
        return conversation.history
