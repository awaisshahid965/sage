"""Chooses a conversation store by name at startup.

Same shape as `sage.llm.factory`: write a class with `load` and `append`, give
its module a `build` function, add a line to `_BUILDERS`.
"""

from collections.abc import Callable

from sage.config import Settings
from sage.conversations import memory, redis
from sage.domain.conversation import ConversationStore

Builder = Callable[[Settings], ConversationStore]

_BUILDERS: dict[str, Builder] = {
    "memory": memory.build,
    "redis": redis.build,
}

STORES = tuple(sorted(_BUILDERS))


def create_conversation_store(settings: Settings) -> ConversationStore:
    """Return the store named by `settings.conversation_store`."""
    try:
        build = _BUILDERS[settings.conversation_store]
    except KeyError:
        raise ValueError(
            f"Unknown conversation store {settings.conversation_store!r}. "
            f"Known stores: {', '.join(STORES)}."
        ) from None

    return build(settings)
