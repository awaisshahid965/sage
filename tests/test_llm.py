"""Tests for the seam itself: the factory and the LangChain adapter."""

from collections.abc import AsyncIterator

import pytest

from sage.config import Settings
from sage.domain.llm import (
    LLMError,
    Message,
    SupportsTokenChoices,
    TokenChoice,
    UnsupportedCapabilityError,
)
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


def test_probability_is_the_exponent_of_the_logprob() -> None:
    assert TokenChoice(token=" Yes", logprob=0.0).probability == 1.0
    assert TokenChoice(token=" Yes", logprob=-0.0294).probability == pytest.approx(
        0.9710, abs=1e-4
    )


def test_only_backends_that_can_do_it_advertise_the_capability() -> None:
    # The whole point of keeping this off ChatModel: echo cannot do it, and
    # says so, without having to implement a fake version.
    assert not isinstance(EchoChatModel(), SupportsTokenChoices)
    assert isinstance(LangChainChatModel(_FakeLangChainModel()), SupportsTokenChoices)  # type: ignore[arg-type]


class _LogprobModel:
    """Returns whatever logprobs payload it is given, like a real provider."""

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.bound: dict[str, object] = {}

    def bind(self, **kwargs: object) -> "_LogprobModel":
        self.bound = kwargs
        return self

    async def ainvoke(self, payload: object) -> object:
        meta = {"logprobs": self._payload}
        return type("Reply", (), {"text": "hi", "response_metadata": meta})()


# Ollama returns pydantic objects, so attribute access.
class _Obj:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)


OLLAMA_SHAPE = [
    _Obj(
        token=" Yes",
        top_logprobs=[
            _Obj(token=" Yes", logprob=-0.03),
            _Obj(token=" Hi", logprob=-3.67),
        ],
    )
]

# OpenAI nests under "content" and uses plain dicts.
OPENAI_SHAPE = {
    "content": [
        {
            "token": " Yes",
            "top_logprobs": [
                {"token": " Yes", "logprob": -0.03},
                {"token": " Hi", "logprob": -3.67},
            ],
        }
    ]
}


@pytest.mark.parametrize(
    "payload", [OLLAMA_SHAPE, OPENAI_SHAPE], ids=["ollama", "openai"]
)
async def test_adapter_reads_both_provider_shapes(payload: object) -> None:
    adapter = LangChainChatModel(_LogprobModel(payload))  # type: ignore[arg-type]

    choices = await adapter.first_token_choices(
        [Message(role="user", content="ship to Berlin?")], top_k=2
    )

    assert [c.token for c in choices] == [" Yes", " Hi"]
    assert choices[0].probability > choices[1].probability


async def test_adapter_asks_for_the_requested_number_of_candidates() -> None:
    inner = _LogprobModel(OLLAMA_SHAPE)
    adapter = LangChainChatModel(inner)  # type: ignore[arg-type]

    await adapter.first_token_choices([Message(role="user", content="x")], top_k=5)

    assert inner.bound == {"logprobs": True, "top_logprobs": 5}


@pytest.mark.parametrize(
    "payload", [None, [], {"content": []}], ids=["none", "empty", "no-entries"]
)
async def test_a_model_without_logprobs_says_so(payload: object) -> None:
    adapter = LangChainChatModel(_LogprobModel(payload))  # type: ignore[arg-type]

    with pytest.raises(UnsupportedCapabilityError):
        await adapter.first_token_choices([Message(role="user", content="x")])


async def test_echo_stream_reassembles_into_complete() -> None:
    model = EchoChatModel()
    messages = [Message(role="user", content="hello there")]

    pieces = [p async for p in model.stream(messages)]

    assert "".join(pieces) == await model.complete(messages)
