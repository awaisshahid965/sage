"""The conversation store: the port's rules, and the adapters that keep them."""

import pytest

from conftest import RecordingChatModel, make_service
from sage.config import Settings
from sage.conversations.factory import create_conversation_store
from sage.conversations.memory import InMemoryConversationStore
from sage.conversations.redis import RedisConversationStore
from sage.domain.llm import Message

TURNS = [
    Message(role="user", content="do you ship to Paris?"),
    Message(role="assistant", content="We do."),
]


class FakeClock:
    """A clock a test can move, so expiry is testable without sleeping."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- the port's central distinction ----------------------------------------


async def test_an_unknown_id_is_none_not_empty() -> None:
    """The whole eviction story rests on this being distinguishable."""
    store = InMemoryConversationStore(ttl_seconds=60)

    assert await store.load("never-existed") is None


async def test_a_stored_conversation_comes_back() -> None:
    store = InMemoryConversationStore(ttl_seconds=60)

    await store.append("abc", TURNS)

    assert await store.load("abc") == TURNS


async def test_append_adds_rather_than_replaces() -> None:
    store = InMemoryConversationStore(ttl_seconds=60)

    await store.append("abc", TURNS[:1])
    await store.append("abc", TURNS[1:])

    assert await store.load("abc") == TURNS


# --- expiry ----------------------------------------------------------------


async def test_a_conversation_expires_after_its_ttl() -> None:
    clock = FakeClock()
    store = InMemoryConversationStore(ttl_seconds=60, clock=clock)
    await store.append("abc", TURNS)

    clock.advance(61)

    assert await store.load("abc") is None


async def test_expiry_measures_silence_not_age() -> None:
    """The TTL slides, so an active conversation is never pulled out from under.

    Without this, a conversation would die a fixed time after it started no
    matter how recently it was used — which is the one moment it must not.
    """
    clock = FakeClock()
    store = InMemoryConversationStore(ttl_seconds=60, clock=clock)

    await store.append("abc", TURNS)
    clock.advance(50)
    await store.append("abc", TURNS)  # still alive, and resets the clock
    clock.advance(50)

    assert await store.load("abc") is not None


async def test_appending_to_an_expired_id_starts_it_over() -> None:
    """An expired conversation does not come back when written to again."""
    clock = FakeClock()
    store = InMemoryConversationStore(ttl_seconds=60, clock=clock)
    await store.append("abc", TURNS)

    clock.advance(61)
    await store.append("abc", [Message(role="user", content="hello?")])

    assert await store.load("abc") == [Message(role="user", content="hello?")]


# --- resolving an id -------------------------------------------------------


async def test_no_id_mints_one() -> None:
    resolved = await make_service(RecordingChatModel()).resolve(None)

    assert resolved.is_new
    assert resolved.conversation_id
    assert resolved.history == []


async def test_a_known_id_is_carried_on() -> None:
    store = InMemoryConversationStore(ttl_seconds=60)
    await store.append("abc", TURNS)
    service = make_service(RecordingChatModel(), store=store)

    resolved = await service.resolve("abc")

    assert not resolved.is_new
    assert resolved.conversation_id == "abc"
    assert resolved.history == TURNS


async def test_an_unknown_id_is_replaced_never_adopted() -> None:
    """A client cannot choose its own id by inventing one and being believed.

    Honouring an unknown id would hand id generation back to the client, which
    is the exact property server-minted ids exist to remove.
    """
    service = make_service(RecordingChatModel())

    resolved = await service.resolve("i-made-this-up")

    assert resolved.is_new
    assert resolved.conversation_id != "i-made-this-up"
    assert resolved.history == []


# --- the factory -----------------------------------------------------------


def test_factory_builds_the_store_named_in_settings() -> None:
    store = create_conversation_store(Settings(conversation_store="memory"))

    assert isinstance(store, InMemoryConversationStore)


def test_factory_builds_the_redis_store_without_connecting() -> None:
    """`Redis.from_url` is lazy, so building must not require a live server."""
    store = create_conversation_store(
        Settings(conversation_store="redis", redis_url="redis://localhost:6379/0")
    )

    assert isinstance(store, RedisConversationStore)


def test_factory_rejects_an_unknown_store() -> None:
    settings = Settings(conversation_store="memory")
    object.__setattr__(settings, "conversation_store", "nope")

    with pytest.raises(ValueError, match="Unknown conversation store"):
        create_conversation_store(settings)
