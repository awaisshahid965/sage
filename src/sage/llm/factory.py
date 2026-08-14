"""Chooses a backend by name at startup.

To add one: write a class with an async `complete`, give its module a `build`
function, and add a line to `_BUILDERS`. That is the whole cost of moving off
LangChain.
"""

from collections.abc import Callable

from sage.config import Settings
from sage.domain.llm import ChatModel
from sage.llm import echo, langchain

# A builder turns settings into a ready model. Every backend exposes one.
Builder = Callable[[Settings], ChatModel]

_BUILDERS: dict[str, Builder] = {
    "langchain": langchain.build,
    "echo": echo.build,
}

BACKENDS = tuple(sorted(_BUILDERS))


def create_chat_model(settings: Settings) -> ChatModel:
    """Return the model named by `settings.llm_backend`."""
    try:
        build = _BUILDERS[settings.llm_backend]
    except KeyError:
        raise ValueError(
            f"Unknown LLM backend {settings.llm_backend!r}. "
            f"Known backends: {', '.join(BACKENDS)}."
        ) from None

    return build(settings)
