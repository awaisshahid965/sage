from httpx import ASGITransport, AsyncClient

from conftest import FailingChatModel, RecordingChatModel
from sage.api.deps import get_sage
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


async def test_backend_failure_becomes_a_502(settings: Settings) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_sage] = lambda: SageService(FailingChatModel())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/chat", json={"question": "hello"})

    assert response.status_code == 502
    # The provider's own message must not leak to the client.
    assert "provider is down" not in response.text
