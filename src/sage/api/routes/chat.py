"""Chat endpoint.

Thin on purpose: parse, call the service, shape the response. The model call
and the prompt live in `sage.application.chat`.
"""

from fastapi import APIRouter

from sage.api.deps import SageDep
from sage.api.schemas import ChatMessage, ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    summary="Ask Sage a question",
    responses={502: {"description": "The model call failed"}},
)
async def chat(body: ChatRequest, sage: SageDep) -> ChatResponse:
    """Answer a single question.

    An `LLMError` from any backend is turned into a 502 by the handler
    registered in `sage.main`.
    """
    reply = await sage.ask(body.question)

    return ChatResponse(reply=ChatMessage(role="assistant", content=reply))
