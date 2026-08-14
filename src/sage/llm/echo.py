"""A backend that needs no network and no API key.

Two jobs:

- Tests and CI run the whole app, end to end, for free and offline.
- It proves the port is real. Two backends exist, and nothing above
  `sage.domain.llm` knows which one is running.
"""

from collections.abc import AsyncIterator, Sequence

from sage.config import Settings
from sage.domain.llm import ChatModel, Message


class EchoChatModel:
    """Repeats the last thing the user said."""

    async def complete(self, messages: Sequence[Message]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return f"You said: {message.content}"
        return "You said nothing."

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        # A word at a time, so the streaming path has something to chew on
        # without a network. Joining the pieces gives back exactly `complete`.
        reply = await self.complete(messages)
        for index, word in enumerate(reply.split(" ")):
            yield word if index == 0 else f" {word}"


def build(settings: Settings) -> ChatModel:
    """Build the echo model. Takes settings so every builder looks the same."""
    del settings
    return EchoChatModel()
