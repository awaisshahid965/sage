"""Several strategies at once."""

from collections.abc import Sequence

from sage.domain.context import ContextStrategy, Conversation
from sage.domain.llm import Message


class Combined:
    """Runs each strategy in turn and concatenates what they return.

    The techniques are not alternatives. A real assistant wants the recent
    turns *and* a summary of the older ones *and* whatever passages match the
    question. Without a way to combine them, the second technique gets bolted
    onto the first, and the resulting class only knows how to be that pair.

    So each strategy stays ignorant of the others, and this composes them:

        Combined(SlidingWindow(8), Passages(store))

    Order is the order the messages reach the model in, which is the only
    coordination between them.

    Runs sequentially. Strategies that do I/O could run concurrently instead,
    but that is a change inside this class and nowhere else.
    """

    def __init__(self, *strategies: ContextStrategy) -> None:
        self._strategies = strategies

    async def select(self, conversation: Conversation) -> Sequence[Message]:
        selected: list[Message] = []
        for strategy in self._strategies:
            selected.extend(await strategy.select(conversation))
        return selected
