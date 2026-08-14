"""LangChain adapter.

`init_chat_model` takes a "<provider>:<model>" string and returns the right
chat model, so changing provider is a config change and nothing else:

    SAGE_LLM_MODEL=openai:gpt-4o-mini
    SAGE_LLM_MODEL=anthropic:claude-haiku-4-5-20251001
    SAGE_LLM_MODEL=google_genai:gemini-2.0-flash

Each provider lives in its own package, so install the one you want
(`uv add langchain-anthropic`) before pointing the setting at it.
"""

from collections.abc import Sequence
from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from sage.config import Settings
from sage.domain.llm import ChatModel, LLMError, Message


class LangChainChatModel:
    """Wraps a LangChain chat model so it satisfies `ChatModel`.

    It takes an already-built model rather than building one itself, which
    keeps the translation logic testable with a fake and keeps all the
    config reading in `build` below.
    """

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def complete(self, messages: Sequence[Message]) -> str:
        # LangChain accepts (role, content) tuples, which is exactly our
        # Message. This is the only place the two shapes have to agree.
        payload = [(message.role, message.content) for message in messages]

        try:
            response = await self._model.ainvoke(payload)
        except Exception as exc:
            # Whatever the SDK threw, callers above only ever see LLMError.
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        # `.text` flattens the reply, which may be plain text or a list of
        # content blocks depending on the provider.
        return response.text


def build(settings: Settings) -> ChatModel:
    """Build a LangChain-backed model from settings."""
    kwargs: dict[str, Any] = {"temperature": settings.llm_temperature}

    # Both are optional. With no key, each provider SDK falls back to its own
    # env var (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...).
    if settings.llm_api_key is not None:
        kwargs["api_key"] = settings.llm_api_key.get_secret_value()
    if settings.llm_base_url is not None:
        kwargs["base_url"] = settings.llm_base_url

    try:
        model = init_chat_model(settings.llm_model, **kwargs)
    except Exception as exc:
        raise LLMError(f"Could not build model {settings.llm_model!r}: {exc}") from exc

    # init_chat_model only returns the configurable variant when asked for
    # one, and we never ask, so this is always a plain BaseChatModel.
    return LangChainChatModel(cast("BaseChatModel", model))
