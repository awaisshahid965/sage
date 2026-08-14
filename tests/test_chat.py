import json

from httpx import ASGITransport, AsyncClient

from conftest import FailingChatModel, FailsMidStreamChatModel, RecordingChatModel
from sage.api.deps import get_sage
from sage.api.routes.chat import MODEL_UNREACHABLE
from sage.application.chat import SYSTEM_PROMPT, SageService
from sage.config import Settings
from sage.main import create_app


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
    service = SageService(model)

    assert await service.ask("do you ship to Berlin?") == "sure"
    assert [(m.role, m.content) for m in model.seen] == [
        ("system", SYSTEM_PROMPT),
        ("user", "do you ship to Berlin?"),
    ]


def parse_sse(body: str) -> list[tuple[str, dict[str, str]]]:
    """Turn a raw SSE body into [(event name, data), ...]."""
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_stream_sends_deltas_then_done(client: AsyncClient) -> None:
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

    assert names[-1] == "done"
    assert set(names[:-1]) == {"delta"}

    # The pieces must reassemble into exactly the non-streamed answer.
    joined = "".join(data["text"] for name, data in events if name == "delta")
    assert joined == "You said: hello"
    assert len(names) > 2, "expected more than one delta, or it is not streaming"


async def test_stream_reports_a_mid_stream_failure_as_an_event(
    settings: Settings,
) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_sage] = lambda: SageService(FailsMidStreamChatModel())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/chat/stream", json={"question": "hello"})

    events = parse_sse(response.text)

    # The status is 200 and cannot be anything else: the model failed after the
    # headers went out. The error has to travel in the body instead.
    assert response.status_code == 200
    assert [name for name, _ in events] == ["delta", "delta", "error"]
    assert events[-1][1]["detail"] == MODEL_UNREACHABLE
    assert "died halfway" not in response.text


async def test_backend_failure_becomes_a_502(settings: Settings) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_sage] = lambda: SageService(FailingChatModel())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/chat", json={"question": "hello"})

    assert response.status_code == 502
    # The provider's own message must not leak to the client.
    assert "provider is down" not in response.text
