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


class ChatRequest(BaseModel):
    """A question for Sage."""

    question: MessageContent


class ChatResponse(BaseModel):
    """The assistant's reply."""

    reply: ChatMessage


class ErrorResponse(BaseModel):
    """What the client gets when a request fails."""

    detail: str
