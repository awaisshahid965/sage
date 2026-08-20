"""Shared fixtures.

`conftest.py` is discovered automatically by pytest — no imports needed in the
test modules themselves.
"""

from collections.abc import AsyncIterator, Sequence

import pytest
from httpx import ASGITransport, AsyncClient

from sage.api.deps import get_sage
from sage.application.chat import SageService
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


def client_for(settings: Settings, service: SageService) -> AsyncClient:
    """The same client, but with the routes pointed at `service`.

    A function rather than a fixture because the service is what the test is
    varying. Use it with `async with`.
    """
    app = create_app(settings)
    app.dependency_overrides[get_sage] = lambda: service
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class RecordingChatModel:
    """A `ChatModel` that stores what it was sent and returns a fixed reply."""

    def __init__(self, reply: str = "hi") -> None:
        self.reply = reply
        self.seen: list[Message] = []

    async def complete(self, messages: Sequence[Message]) -> str:
        self.seen = list(messages)
        return self.reply

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        self.seen = list(messages)
        for char in self.reply:
            yield char


class FailingChatModel:
    """A `ChatModel` that always fails, the way a real backend would."""

    async def complete(self, messages: Sequence[Message]) -> str:
        raise LLMError("provider is down")

    def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        # A plain `def` that raises satisfies the protocol too. This one fails
        # on the call; `FailsMidStreamChatModel` fails during iteration.
        raise LLMError("provider is down")


class FailsMidStreamChatModel:
    """Sends a few pieces, then dies. The case a 502 cannot express."""

    async def complete(self, messages: Sequence[Message]) -> str:
        raise LLMError("provider is down")

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        yield "partial "
        yield "answer "
        raise LLMError("provider died halfway")
