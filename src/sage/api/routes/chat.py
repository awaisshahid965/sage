"""Chat endpoints.

Thin on purpose: parse, call the service, shape the response. The model call
and the prompt live in `sage.application.chat`.
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from sage.api.deps import SageDep
from sage.api.schemas import ChatMessage, ChatRequest, ChatResponse
from sage.domain.llm import LLMError, Message
from sage.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

MODEL_UNREACHABLE = "The language model could not be reached."


def _history(body: ChatRequest) -> list[Message]:
    """Convert replayed wire turns into domain messages.

    Crossing that boundary is the route's job, and it is the whole reason the
    two types are separate. Nothing is re-validated here: pydantic already
    checked this input, and past that point the app trusts its own values.
    """
    return [Message(role=turn.role, content=turn.content) for turn in body.history]


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
    reply = await sage.ask(body.question, _history(body))

    return ChatResponse(reply=ChatMessage(role="assistant", content=reply))


def _event(name: str, data: dict[str, str]) -> str:
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

    Emits three kinds of event: `delta` for each piece of the answer, then
    either `done` or `error`.

    Failures cannot use the 502 handler here. By the time the model fails, a
    200 and its headers are already on the wire, and a status code cannot be
    taken back. So the error is caught inside the generator and reported as an
    `error` event. A client must treat that as a failure even though the HTTP
    status said 200.
    """

    async def events() -> AsyncIterator[str]:
        try:
            # Awaited inside the generator, so a strategy that fails while
            # assembling context is reported the same way a failing model is.
            # By the time this body runs the 200 is already committed either
            # way, so there is no branch here that could still be a 502.
            deltas = await sage.ask_stream(body.question, _history(body))
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
