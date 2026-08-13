from httpx import AsyncClient


async def test_chat_replies_to_the_latest_message(client: AsyncClient) -> None:
    response = await client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == {
        "role": "assistant",
        "content": "You said: hello",
    }


async def test_chat_rejects_an_empty_conversation(client: AsyncClient) -> None:
    response = await client.post("/chat", json={"messages": []})

    assert response.status_code == 422
