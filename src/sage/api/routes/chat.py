"""Chat endpoints.

Thin on purpose: parse, call the service, shape the response. The model call,
the prompt and the conversation rules live in `sage.application.chat`.
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from sage.api.deps import SageDep
from sage.api.schemas import ChatMessage, ChatRequest, ChatResponse
from sage.domain.llm import LLMError
from sage.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

MODEL_UNREACHABLE = "The language model could not be reached."


@router.post(
    "",
    summary="Ask Sage a question",
    responses={502: {"description": "The model call failed"}},
)
async def chat(body: ChatRequest, sage: SageDep) -> ChatResponse:
    """Answer a single question, all at once.

    An `LLMError` from any backend is turned into a 502 by the handler
    registered in `sage.main`.
    """
    answer = await sage.ask(body.question, body.conversation_id)

    return ChatResponse(
        reply=ChatMessage(role="assistant", content=answer.reply),
        conversation_id=answer.conversation.conversation_id,
        # Only a restart the client did not ask for is worth reporting. A
        # request that sent no id was starting fresh on purpose.
        conversation_restarted=answer.conversation.is_new
        and body.conversation_id is not None,
    )


def _event(name: str, data: dict[str, object]) -> str:
    """Format one Server-Sent Event.

    The payload is JSON rather than raw text because SSE separates frames with
    newlines, and a model chunk can contain one. JSON escapes it, so a newline
    in the answer cannot break the framing.
    """
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


@router.post(
    "/stream",
    summary="Ask Sage a question, streamed",
    response_class=StreamingResponse,
)
async def chat_stream(body: ChatRequest, sage: SageDep) -> StreamingResponse:
    """Answer a single question, sending each piece as the model produces it.

    Emits `conversation` first, then a `delta` per piece, then `done` or
    `error`.

    `conversation` leads deliberately. If the id sent had expired, the client
    is about to receive an answer written with none of the history still on its
    screen, and it needs to know that before the text arrives rather than after.

    Failures cannot use the 502 handler here. By the time the model fails, a
    200 and its headers are already on the wire, and a status code cannot be
    taken back. So the error is caught inside the generator and reported as an
    `error` event. A client must treat that as a failure even though the HTTP
    status said 200.
    """

    async def events() -> AsyncIterator[str]:
        try:
            conversation, deltas = await sage.ask_stream(
                body.question, body.conversation_id
            )
        except LLMError as exc:
            log.error("stream_setup_failed", error=str(exc))
            yield _event("error", {"detail": MODEL_UNREACHABLE})
            return

        yield _event(
            "conversation",
            {
                "conversation_id": conversation.conversation_id,
                "restarted": conversation.is_new and body.conversation_id is not None,
            },
        )

        try:
            async for delta in deltas:
                yield _event("delta", {"text": delta})
        except LLMError as exc:
            log.error("stream_failed", error=str(exc))
            yield _event("error", {"detail": MODEL_UNREACHABLE})
        else:
            yield _event("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells nginx not to buffer, which would defeat the whole point.
            "X-Accel-Buffering": "no",
        },
    )
