"""The chat use case: build the prompt, call the model, hand back the text."""

from collections.abc import AsyncIterator

from sage.domain.llm import ChatModel, Message

SYSTEM_PROMPT = (
    "You're a friendly support agent for Pebble, an online gadget store. "
    "Answer the customer's question."
)


class SageService:
    """Answers questions.

    It depends on `ChatModel`, not on LangChain, so it does not change when
    the backend does. Tests pass it a fake and never touch the network.
    """

    def __init__(self, model: ChatModel, system_prompt: str = SYSTEM_PROMPT) -> None:
        self._model = model
        self._system_prompt = system_prompt

    def _prompt(self, question: str) -> list[Message]:
        """Build the turns to send. Both ways of asking share this."""
        return [
            Message(role="system", content=self._system_prompt),
            Message(role="user", content=question),
        ]

    async def ask(self, question: str) -> str:
        """Answer one question. Raises `LLMError` if the model call fails."""
        return await self._model.complete(self._prompt(question))

    def ask_stream(self, question: str) -> AsyncIterator[str]:
        """Answer one question in pieces, as the model produces them.

        A plain `def` returning the model's iterator, so there is no extra
        generator wrapped around it. The `LLMError` surfaces while the caller
        is iterating, not when this is called.
        """
        return self._model.stream(self._prompt(question))
