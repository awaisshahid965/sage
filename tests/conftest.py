"""Shared fixtures.

`conftest.py` is discovered automatically by pytest — no imports needed in the
test modules themselves.
"""

from collections.abc import AsyncIterator, Sequence

import pytest
from httpx import ASGITransport, AsyncClient

from sage.config import Settings
from sage.domain.llm import LLMError, Message
from sage.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Settings for a test run, independent of the developer's `.env`.

    The echo backend means the suite needs no API key and makes no network
    call, so CI runs the real app end to end.
    """
    return Settings(environment="test", log_level="WARNING", llm_backend="echo")


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired straight to the ASGI app — no socket, no server."""
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class RecordingChatModel:
    """A `ChatModel` that stores what it was sent and returns a fixed reply."""

    def __init__(self, reply: str = "hi") -> None:
        self.reply = reply
        self.seen: list[Message] = []

    async def complete(self, messages: Sequence[Message]) -> str:
        self.seen = list(messages)
        return self.reply


class FailingChatModel:
    """A `ChatModel` that always fails, the way a real backend would."""

    async def complete(self, messages: Sequence[Message]) -> str:
        raise LLMError("provider is down")
