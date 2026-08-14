"""Tests for the seam itself: the factory and the LangChain adapter."""

from collections.abc import AsyncIterator

import pytest

from sage.config import Settings
from sage.domain.llm import LLMError, Message
from sage.llm.echo import EchoChatModel
from sage.llm.factory import create_chat_model
from sage.llm.langchain import LangChainChatModel


def test_factory_builds_the_backend_named_in_settings() -> None:
    model = create_chat_model(Settings(llm_backend="echo"))

    assert isinstance(model, EchoChatModel)


def test_factory_rejects_an_unknown_backend() -> None:
    settings = Settings(llm_backend="echo")
    # Bypass the Literal so we can test the runtime guard.
    object.__setattr__(settings, "llm_backend", "nope")

    with pytest.raises(ValueError, match="Unknown LLM backend"):
        create_chat_model(settings)


class _FakeLangChainModel:
    """Stands in for a LangChain chat model."""

    def __init__(self, text: str = "hello", error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.payload: object = None

    async def ainvoke(self, payload: object) -> object:
        self.payload = payload
        if self._error is not None:
            raise self._error
        return type("Reply", (), {"text": self._text})()

    async def astream(self, payload: object) -> AsyncIterator[object]:
        self.payload = payload
        if self._error is not None:
            raise self._error
        chunk = type("Chunk", (), {"text": ""})
        yield chunk()  # empty chunk, must be skipped
        for word in self._text.split(" "):
            yield type("Chunk", (), {"text": word})()


async def test_adapter_converts_messages_to_role_content_tuples() -> None:
    fake = _FakeLangChainModel(text="hi there")
    adapter = LangChainChatModel(fake)  # type: ignore[arg-type]

    reply = await adapter.complete(
        [Message(role="system", content="be nice"), Message(role="user", content="yo")]
    )

    assert reply == "hi there"
    assert fake.payload == [("system", "be nice"), ("user", "yo")]


async def test_adapter_wraps_provider_errors_in_llm_error() -> None:
    fake = _FakeLangChainModel(error=RuntimeError("429 rate limited"))
    adapter = LangChainChatModel(fake)  # type: ignore[arg-type]

    with pytest.raises(LLMError, match="429 rate limited"):
        await adapter.complete([Message(role="user", content="yo")])


async def test_adapter_streams_chunks_and_skips_empty_ones() -> None:
    fake = _FakeLangChainModel(text="hi there you")
    adapter = LangChainChatModel(fake)  # type: ignore[arg-type]

    pieces = [p async for p in adapter.stream([Message(role="user", content="yo")])]

    assert pieces == ["hi", "there", "you"]


async def test_adapter_wraps_stream_errors_in_llm_error() -> None:
    fake = _FakeLangChainModel(error=RuntimeError("connection reset"))
    adapter = LangChainChatModel(fake)  # type: ignore[arg-type]

    with pytest.raises(LLMError, match="connection reset"):
        [p async for p in adapter.stream([Message(role="user", content="yo")])]


async def test_echo_stream_reassembles_into_complete() -> None:
    model = EchoChatModel()
    messages = [Message(role="user", content="hello there")]

    pieces = [p async for p in model.stream(messages)]

    assert "".join(pieces) == await model.complete(messages)
