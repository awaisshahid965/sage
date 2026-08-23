"""Request and response models: the wire contract.

They validate untrusted input, serialise output, and generate the OpenAPI
schema.

On the overlap with `sage.domain.llm.Message` — the two look alike and stay
separate on purpose:

- This file is public. Changing it breaks clients and needs a version bump.
  `Message` is internal and free to change any time.
- This file distrusts its input, so it has length limits. `Message` is built
  by our own code from values already checked, so it has none.
- Merging them would turn every internal refactor into a breaking API change,
  and would put pydantic in the domain layer.

What they do share is vocabulary, not structure, and vocabulary has exactly
one home: the domain. Hence the `Role` import below.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from sage.domain.llm import Role

# Every field carrying user or model text uses this, so the limits are stated
# once. Widen it here and both the question and the reply follow.
MessageContent = Annotated[str, Field(min_length=1, max_length=32_000)]


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: Literal["ok"] = "ok"
    version: str
    environment: str


class ChatMessage(BaseModel):
    """A single turn in a conversation, as it appears on the wire."""

    role: Role
    content: MessageContent


# A narrowing of the domain's `Role`, not a second vocabulary. The client
# reads what was *said*; it does not get to say who Sage is. The system prompt
# is the service's (see `sage.application.chat`), and leaving it out of the
# wire type keeps that ownership a fact of the schema rather than a rule
# someone has to remember.
HistoryRole = Literal["user", "assistant"]

# Long enough for any id Sage mints, short enough that a client cannot use the
# field as a place to put a payload. Unknown ids are rejected by being unknown,
# not by their shape, so this is a size limit and nothing more.
ConversationId = Annotated[str, Field(min_length=1, max_length=64)]


class ChatTurn(BaseModel):
    """One turn of a stored conversation."""

    role: HistoryRole
    content: MessageContent


class ChatRequest(BaseModel):
    """A question for Sage, and the conversation it belongs to.

    The client sends an id, not a history. Sage holds the turns, so a client
    cannot claim the assistant said something it did not — which is the whole
    reason conversations moved server-side.

    Omit `conversation_id` to start a new conversation. Send one Sage does not
    recognise and it starts a new one anyway, returning the new id: an id is a
    key that may or may not open something, never a claim that it should.
    """

    question: MessageContent
    conversation_id: ConversationId | None = None


class ChatResponse(BaseModel):
    """The assistant's reply, and the conversation it belongs to.

    `conversation_id` comes back on every response, not only the first. The
    client stores whatever it is told and sends it next time, which means the
    "your conversation expired, here is a new one" case needs no special
    handling on the client beyond noticing `conversation_restarted`.
    """

    reply: ChatMessage
    conversation_id: str

    # True when the id sent was not honoured — expired, evicted, or never
    # existed — and this reply was produced with no history behind it.
    conversation_restarted: bool = False


class ConversationResponse(BaseModel):
    """A stored conversation, as the client picks it up after a reload."""

    conversation_id: str
    messages: list[ChatTurn]


class ErrorResponse(BaseModel):
    """What the client gets when a request fails."""

    detail: str
