"""Chat endpoint.

A deliberately trivial echo for now — the point of the scaffold is the shape of
the seam, not the model behind it. Swap the body of `chat` for a real assistant
once there is one to call.
"""

from fastapi import APIRouter

from sage.api.schemas import ChatMessage, ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", summary="Continue a conversation")
async def chat(request: ChatRequest) -> ChatResponse:
    """Return a reply to the most recent message."""
    latest = request.messages[-1]
    return ChatResponse(
        reply=ChatMessage(role="assistant", content=f"You said: {latest.content}")
    )
