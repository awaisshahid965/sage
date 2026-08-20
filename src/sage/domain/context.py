"""The context port.

A prompt has three parts, and only the middle one is interesting:

    [ system prompt ]   who Sage is. The service owns this.
    [ context       ]   everything else the model should know. This file.
    [ the question  ]   what was just asked. The service owns this.

"Context" is one job with many possible answers. Today it is the whole
conversation so far. Later it is *some* of the conversation (a sliding window),
or a summary of the older turns, or passages pulled from Pebble's policy
documents, or all three at once. Those differ enormously in cost and machinery
-- a window is a slice, a summary is a second model call, passages need
embeddings and a vector store -- and not at all in what the caller wants from
them: some messages to put in front of the model.

So the choice is a strategy, not a branch. `SageService` asks for messages and
never learns which technique produced them, exactly as it asks `ChatModel` for
a reply and never learns which provider produced it. This is the same seam as
`sage.domain.llm`, cut in the other direction: that one abstracts *who answers*,
this one abstracts *what they are told*.

Adding retrieval later is a new class and one line in `sage.main`. Nothing above
this file moves.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sage.domain.llm import Message


@dataclass(frozen=True, slots=True)
class Conversation:
    """What a strategy is given to work with.

    A type rather than two loose arguments, because strategies will want more
    over time -- a conversation id, a token budget, who is asking -- and adding
    a field here leaves every existing strategy's signature alone.

    `history` is the turns already exchanged, oldest first, and excludes
    `question`. The current question is separate because most strategies treat
    it differently from the rest: a retriever searches *with* it, a window
    counts *without* it, and the service appends it last either way.
    """

    question: str
    history: Sequence[Message] = ()


class ContextStrategy(Protocol):
    """Decides what the model sees besides the system prompt and the question.

    Any class with this method works, so strategies subclass nothing.
    """

    async def select(self, conversation: Conversation) -> Sequence[Message]:
        """Return the messages to sit between the system prompt and the question.

        Async because the interesting implementations do I/O: a summariser
        calls a model, a retriever queries a vector store. `FullHistory` awaits
        nothing and pays nothing for the shape.

        "Select" is loose on purpose. A strategy may hand back turns unchanged,
        hand back fewer of them, or hand back something it wrote itself -- a
        summary and a block of retrieved passages are both good context that
        nobody ever actually said.
        """
        ...
