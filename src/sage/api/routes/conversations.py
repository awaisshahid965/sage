"""Reading a conversation back.

What a page reload uses. The client holds an id and nothing else, so this is
how it finds out whether that id still means anything and what was said under
it.
"""

from fastapi import APIRouter, HTTPException

from sage.api.deps import SageDep
from sage.api.schemas import ChatTurn, ConversationResponse, ErrorResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])

NOT_FOUND = "No conversation is stored under that id."


@router.get(
    "/{conversation_id}",
    summary="Read a stored conversation",
    responses={404: {"model": ErrorResponse, "description": "Unknown or expired"}},
)
async def get_conversation(conversation_id: str, sage: SageDep) -> ConversationResponse:
    """Return the turns stored under `conversation_id`.

    404 means the id points at nothing — expired, evicted, or never real. The
    three are deliberately indistinguishable: telling a caller which one it was
    would confirm that some ids exist and others do not, and the client's
    response is the same either way. Forget the id and start fresh.

    A 404 is the honest status here rather than an empty 200. The client is
    asking for a specific thing, and it is not there.
    """
    turns = await sage.history(conversation_id)

    if turns is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)

    return ConversationResponse(
        conversation_id=conversation_id,
        messages=[
            ChatTurn(role=turn.role, content=turn.content)
            for turn in turns
            # The store holds only what the service wrote, which is never a
            # system turn — but the wire type allows two roles and this keeps
            # that a fact rather than an assumption.
            if turn.role in {"user", "assistant"}
        ],
    )
