"""Request and response models.

Pydantic models are the contract: they validate input, serialise output, and
generate the OpenAPI schema. Keep them separate from any future persistence
models so the wire format can evolve independently of storage.
"""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: Literal["ok"] = "ok"
    version: str
    environment: str


class ChatMessage(BaseModel):
    """A single turn in a conversation."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32_000)


class ChatRequest(BaseModel):
    """A conversation to continue."""

    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    """The assistant's reply."""

    reply: ChatMessage
