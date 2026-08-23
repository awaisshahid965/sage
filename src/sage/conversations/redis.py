"""Redis adapter for the conversation store.

One key per conversation holding a JSON list of turns, with a TTL. Redis owns
expiry, so nothing in the app has to sweep anything or check a timestamp — a
conversation that timed out simply is not there, which is precisely what the
port's `None` means.

Named `redis.py` beside `redis` the package, the same way `sage.llm.langchain`
sits beside `langchain`. Python 3 imports are absolute, so `from redis.asyncio
import Redis` below reaches the real library, not this module.
"""

import json
from collections.abc import Sequence
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from sage.config import Settings
from sage.domain.conversation import ConversationStore
from sage.domain.llm import Message

# Namespaced and versioned. The prefix keeps conversations distinguishable from
# anything else sharing the database; the version means a future change to the
# stored shape can be a new prefix rather than a migration.
KEY_PREFIX = "sage:conversation:v1:"


class ConversationStoreError(RuntimeError):
    """The store could not be reached.

    The same bargain `LLMError` makes: the API layer never imports `redis` to
    handle a failure, and swapping the backing store does not move any error
    handling.
    """


def _key(conversation_id: str) -> str:
    return f"{KEY_PREFIX}{conversation_id}"


class RedisConversationStore:
    """Conversations in Redis, one JSON list per key.

    Takes an already-built client rather than building one, which keeps the
    translation testable against a fake and keeps config reading in `build`.
    """

    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl = ttl_seconds

    async def load(self, conversation_id: str) -> list[Message] | None:
        try:
            raw = await self._client.get(_key(conversation_id))
        except RedisError as exc:
            raise ConversationStoreError(f"{type(exc).__name__}: {exc}") from exc

        if raw is None:
            return None

        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            # Someone wrote something else under our key, or an older build
            # used a different shape. Unreadable is indistinguishable from
            # absent as far as the caller can act on it.
            return None

        if not isinstance(stored, list):
            return None

        return [
            Message(role=turn["role"], content=turn["content"])
            for turn in cast("list[dict[str, Any]]", stored)
            if isinstance(turn, dict) and turn.get("role") in {"user", "assistant"}
        ]

    async def append(self, conversation_id: str, turns: Sequence[Message]) -> None:
        # Read-modify-write. Two requests appending to the same conversation at
        # the same moment could lose one of them — which needs a WATCH or a
        # Lua script to fix properly, and does not arise while a conversation
        # has one client sending one question at a time.
        existing = await self.load(conversation_id) or []
        merged = [*existing, *turns]

        payload = json.dumps(
            [{"role": turn.role, "content": turn.content} for turn in merged]
        )

        try:
            # SET with `ex` writes the value and the deadline together, so the
            # key is never briefly immortal between two commands. The TTL is
            # rewritten every time, which is what makes expiry slide.
            await self._client.set(_key(conversation_id), payload, ex=self._ttl)
        except RedisError as exc:
            raise ConversationStoreError(f"{type(exc).__name__}: {exc}") from exc


def build(settings: Settings) -> ConversationStore:
    """Build a Redis-backed store from settings."""
    client: Redis = Redis.from_url(
        settings.redis_url,
        # Values come back as `str`, so `json.loads` does not have to care
        # whether it was handed bytes.
        decode_responses=True,
    )
    return RedisConversationStore(client, ttl_seconds=settings.conversation_ttl_seconds)
