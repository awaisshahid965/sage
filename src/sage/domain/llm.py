"""The LLM port.

This file is the seam. It imports nothing from LangChain, OpenAI, or FastAPI,
and it never will. Everything above it depends on `ChatModel` only.

So there are two kinds of switch, and both are cheap:

- New provider (OpenAI -> Anthropic): a config change. See `sage.llm.langchain`.
- New framework (LangChain -> something else): one new class with a `complete`
  method, registered in `sage.llm.factory`. Nothing above this file moves.
"""

import math
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

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


@dataclass(frozen=True, slots=True)
class TokenChoice:
    """One token the model considered at a single step, and how likely it was.

    A language model does not choose a word. At every step it produces a score
    for every token it knows, turns those into a probability distribution, and
    samples one. This type is a single entry from that distribution.
    """

    token: str
    logprob: float

    @property
    def probability(self) -> float:
        """The same number as a plain 0-to-1 probability.

        Models report *log* probabilities. Generating a sentence means
        multiplying many numbers below 1, which underflows to zero fast.
        Adding logarithms does not. `exp` undoes the log.
        """
        return math.exp(self.logprob)


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


class UnsupportedCapabilityError(LLMError):
    """The backend cannot do the thing that was asked of it.

    Different from a call that failed. Nothing went wrong; this model just
    does not offer the feature.
    """


@runtime_checkable
class SupportsTokenChoices(Protocol):
    """An optional extra, kept off `ChatModel` on purpose.

    Not every backend can do this. `echo` has no distribution at all, and some
    providers never return one. Adding it to `ChatModel` would force every
    adapter to implement or fake it, which is how a small port turns into a
    big one.

    A separate protocol keeps the core port honest. Callers ask
    `isinstance(model, SupportsTokenChoices)` first and degrade politely when
    the answer is no. That check works because of `@runtime_checkable`, which
    verifies the method exists (it does not check the signature).
    """

    async def first_token_choices(
        self, messages: Sequence[Message], top_k: int = 5
    ) -> list[TokenChoice]:
        """Return the `top_k` most likely candidates for the *first* token.

        Raises `UnsupportedCapabilityError` if the provider returns nothing.
        """
        ...
