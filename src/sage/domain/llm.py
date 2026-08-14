"""The LLM port.

This file is the seam. It imports nothing from LangChain, OpenAI, or FastAPI,
and it never will. Everything above it depends on `ChatModel` only.

So there are two kinds of switch, and both are cheap:

- New provider (OpenAI -> Anthropic): a config change. See `sage.llm.langchain`.
- New framework (LangChain -> something else): one new class with a `complete`
  method, registered in `sage.llm.factory`. Nothing above this file moves.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

# The one definition of who can speak. `sage.api.schemas` imports this rather
# than repeating the literal, so adding a role (say "tool") is a single edit.
# Layers point inward: the API may read the domain's vocabulary, never the
# reverse.
Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    """One turn in a conversation, inside the app.

    A plain dataclass, not a pydantic model, and that is deliberate. These are
    built by our own code from values the API already validated, so re-checking
    them would cost time and buy nothing. Validate once, at the edge; trust
    what is already inside. It also keeps pydantic out of the domain.

    `sage.api.schemas.ChatMessage` is the wire twin of this type. See that
    module for why they are not one class.
    """

    role: Role
    content: str


class LLMError(RuntimeError):
    """A call to the model failed.

    Adapters catch whatever their SDK raises and re-raise this. That way the
    API layer never has to import `openai` to handle an error, and swapping
    the provider does not change the error handling.
    """


class ChatModel(Protocol):
    """All Sage needs from a language model.

    Any class with these methods works, so adapters do not subclass anything.
    """

    async def complete(self, messages: Sequence[Message]) -> str:
        """Send `messages` and return the assistant's reply as text."""
        ...

    def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """Send `messages` and yield the reply in pieces as it arrives.

        Joining every piece gives the same text `complete` would return.
        Note this is a plain `def` returning an iterator, not an `async def`.
        An `async def` with `yield` in it already satisfies this.
        """
        ...
