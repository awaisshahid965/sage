"""The chat use case: build the prompt, call the model, hand back the text."""

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

    async def ask(self, question: str) -> str:
        """Answer one question. Raises `LLMError` if the model call fails."""
        return await self._model.complete(
            [
                Message(role="system", content=self._system_prompt),
                Message(role="user", content=question),
            ]
        )
