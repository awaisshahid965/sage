import json

from httpx import AsyncClient

from conftest import (
    FailingChatModel,
    FailsMidStreamChatModel,
    RecordingChatModel,
    client_for,
    make_service,
)
from sage.api.routes.chat import MODEL_UNREACHABLE
from sage.application.chat import SYSTEM_PROMPT
from sage.config import Settings
from sage.conversations.memory import InMemoryConversationStore


async def test_chat_answers_a_question(client: AsyncClient) -> None:
    response = await client.post("/chat", json={"question": "hello"})

    assert response.status_code == 200
    assert response.json()["reply"] == {
        "role": "assistant",
        "content": "You said: hello",
    }


async def test_chat_rejects_an_empty_question(client: AsyncClient) -> None:
    response = await client.post("/chat", json={"question": ""})

    assert response.status_code == 422


async def test_chat_rejects_a_missing_question(client: AsyncClient) -> None:
    response = await client.post("/chat", json={})

    assert response.status_code == 422


async def test_service_sends_the_system_prompt_then_the_question() -> None:
    model = RecordingChatModel(reply="sure")
    service = make_service(model)

    answer = await service.ask("do you ship to Berlin?")

    assert answer.reply == "sure"
    assert [(m.role, m.content) for m in model.seen] == [
        ("system", SYSTEM_PROMPT),
        ("user", "do you ship to Berlin?"),
    ]


# --- conversation ids ------------------------------------------------------


async def test_a_first_request_gets_an_id_back(client: AsyncClient) -> None:
    response = await client.post("/chat", json={"question": "hello"})

    body = response.json()
    assert body["conversation_id"]
    # Nothing was restarted: the client never claimed a conversation.
    assert body["conversation_restarted"] is False


async def test_the_second_turn_can_see_the_first(settings: Settings) -> None:
    """The point of the whole change, now with the server holding the turns."""
    model = RecordingChatModel(reply="We do, in 3-5 days.")

    async with client_for(settings, make_service(model)) as ac:
        first = await ac.post("/chat", json={"question": "do you ship to Paris?"})
        conversation_id = first.json()["conversation_id"]

        second = await ac.post(
            "/chat",
            json={"question": "and to Berlin?", "conversation_id": conversation_id},
        )

    assert second.json()["conversation_id"] == conversation_id
    assert [(m.role, m.content) for m in model.seen] == [
        ("system", SYSTEM_PROMPT),
        ("user", "do you ship to Paris?"),
        ("assistant", "We do, in 3-5 days."),
        ("user", "and to Berlin?"),
    ]


async def test_an_evicted_id_is_replaced_and_reported(settings: Settings) -> None:
    """The case that needed designing: the client's id no longer points at anything.

    The reply is produced with no history, a new id comes back, and the flag
    says so — the client has messages on screen the server has never heard of
    and must be told rather than left to infer it.
    """
    model = RecordingChatModel(reply="ok")

    async with client_for(settings, make_service(model)) as ac:
        response = await ac.post(
            "/chat",
            json={"question": "and to Berlin?", "conversation_id": "long-gone"},
        )

    body = response.json()
    assert body["conversation_restarted"] is True
    assert body["conversation_id"] != "long-gone"
    # No history reached the model: there was none to reach it.
    assert [(m.role, m.content) for m in model.seen] == [
        ("system", SYSTEM_PROMPT),
        ("user", "and to Berlin?"),
    ]


async def test_a_failed_exchange_is_not_remembered(settings: Settings) -> None:
    """A question with no answer must not be replayed as though it had one."""
    store = InMemoryConversationStore(ttl_seconds=3600)

    async with client_for(
        settings, make_service(FailingChatModel(), store=store)
    ) as ac:
        response = await ac.post("/chat", json={"question": "hello"})

    assert response.status_code == 502
    # Nothing was written, so there is no id to have written it under either.
    assert await store.load("anything") is None


async def test_chat_rejects_an_oversized_conversation_id(client: AsyncClient) -> None:
    response = await client.post(
        "/chat", json={"question": "hello", "conversation_id": "x" * 65}
    )

    assert response.status_code == 422


# --- reading a conversation back -------------------------------------------


async def test_a_conversation_can_be_read_back(settings: Settings) -> None:
    """What a page reload does."""
    async with client_for(settings, make_service(RecordingChatModel("We do."))) as ac:
        first = await ac.post("/chat", json={"question": "do you ship to Paris?"})
        conversation_id = first.json()["conversation_id"]

        response = await ac.get(f"/conversations/{conversation_id}")

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": conversation_id,
        "messages": [
            {"role": "user", "content": "do you ship to Paris?"},
            {"role": "assistant", "content": "We do."},
        ],
    }


async def test_reading_an_unknown_conversation_is_a_404(client: AsyncClient) -> None:
    """How the client learns to forget the id in its storage."""
    response = await client.get("/conversations/long-gone")

    assert response.status_code == 404


# --- streaming -------------------------------------------------------------


def parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    """Turn a raw SSE body into [(event name, data), ...]."""
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_stream_sends_the_conversation_then_deltas_then_done(
    client: AsyncClient,
) -> None:
    """Checks the framing and the content, not the timing.

    `ASGITransport` collects the whole body before handing it back, so these
    tests cannot show that pieces arrive early — they would pass even if the
    endpoint buffered. Incremental delivery was verified separately against a
    real uvicorn socket: 210 deltas spread over 21s. If you change the
    streaming path, re-check it that way, not here.
    """
    response = await client.post("/chat/stream", json={"question": "hello"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    names = [name for name, _ in events]

    # The id leads, so a client knows which conversation it is reading before
    # any of the answer arrives.
    assert names[0] == "conversation"
    assert events[0][1]["conversation_id"]
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"delta"}

    joined = "".join(str(data["text"]) for name, data in events if name == "delta")
    assert joined == "You said: hello"
    assert len(names) > 3, "expected more than one delta, or it is not streaming"


async def test_stream_remembers_the_exchange(settings: Settings) -> None:
    """A streamed answer is stored once it finishes, like any other."""
    async with client_for(settings, make_service(RecordingChatModel("hi"))) as ac:
        response = await ac.post("/chat/stream", json={"question": "hello"})
        conversation_id = parse_sse(response.text)[0][1]["conversation_id"]

        stored = await ac.get(f"/conversations/{conversation_id}")

    assert [m["content"] for m in stored.json()["messages"]] == ["hello", "hi"]


async def test_stream_reports_an_evicted_id_before_the_answer(
    settings: Settings,
) -> None:
    async with client_for(settings, make_service(RecordingChatModel())) as ac:
        response = await ac.post(
            "/chat/stream",
            json={"question": "hello", "conversation_id": "long-gone"},
        )

    name, data = parse_sse(response.text)[0]

    assert name == "conversation"
    assert data["restarted"] is True
    assert data["conversation_id"] != "long-gone"


async def test_stream_reports_a_mid_stream_failure_as_an_event(
    settings: Settings,
) -> None:
    service = make_service(FailsMidStreamChatModel())

    async with client_for(settings, service) as ac:
        response = await ac.post("/chat/stream", json={"question": "hello"})

    events = parse_sse(response.text)

    # The status is 200 and cannot be anything else: the model failed after the
    # headers went out. The error has to travel in the body instead.
    assert response.status_code == 200
    assert [name for name, _ in events] == [
        "conversation",
        "delta",
        "delta",
        "error",
    ]
    assert events[-1][1]["detail"] == MODEL_UNREACHABLE
    assert "died halfway" not in response.text


async def test_a_half_finished_stream_is_not_remembered(settings: Settings) -> None:
    """Half an answer is not something to replay into a later prompt."""
    store = InMemoryConversationStore(ttl_seconds=3600)
    service = make_service(FailsMidStreamChatModel(), store=store)

    async with client_for(settings, service) as ac:
        response = await ac.post("/chat/stream", json={"question": "hello"})
        conversation_id = parse_sse(response.text)[0][1]["conversation_id"]

    assert await store.load(str(conversation_id)) is None


async def test_backend_failure_becomes_a_502(settings: Settings) -> None:
    service = make_service(FailingChatModel())

    async with client_for(settings, service) as ac:
        response = await ac.post("/chat", json={"question": "hello"})

    assert response.status_code == 502
    # The provider's own message must not leak to the client.
    assert "provider is down" not in response.text
