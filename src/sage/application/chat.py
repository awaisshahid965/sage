"""The chat use case: build the prompt, call the model, hand back the text."""

from collections.abc import AsyncIterator, Sequence

from sage.domain.context import ContextStrategy, Conversation
from sage.domain.llm import ChatModel, Message

SYSTEM_PROMPT = (
    "You're a friendly support agent for Pebble, an online gadget store. "
    "Answer the customer's question."
)


class SageService:
    """Answers questions.

    It depends on two ports and no vendor: `ChatModel` decides who answers,
    `ContextStrategy` decides what they are told. Neither is defaulted here --
    `sage.main` is the one file that knows which implementations are running.
    Tests pass fakes for both and never touch the network.
    """

    def __init__(
        self,
        model: ChatModel,
        context: ContextStrategy,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self._model = model
        self._context = context
        self._system_prompt = system_prompt

    async def _prompt(self, question: str, history: Sequence[Message]) -> list[Message]:
        """Build the turns to send. Both ways of asking share this.

        The frame is fixed and belongs to the service: instructions first, the
        live question last, wherever it came from. Everything between the two
        is the strategy's to decide, and this method does not know or care
        whether it got replayed turns, a summary, or retrieved passages.
        """
        conversation = Conversation(question=question, history=history)

        return [
            Message(role="system", content=self._system_prompt),
            *await self._context.select(conversation),
            Message(role="user", content=question),
        ]

    async def ask(self, question: str, history: Sequence[Message] = ()) -> str:
        """Answer one question. Raises `LLMError` if the model call fails."""
        return await self._model.complete(await self._prompt(question, history))

    async def ask_stream(
        self, question: str, history: Sequence[Message] = ()
    ) -> AsyncIterator[str]:
        """Answer one question in pieces, as the model produces them.

        An `async def` that *returns* the model's iterator rather than yielding
        through one of its own. There is no `yield` in this body, so awaiting
        it assembles the prompt and hands back the model's own stream -- the
        `LLMError` from a failing model still surfaces while the caller
        iterates, not here.

        It has to be awaited now, because building the prompt can do I/O: a
        summarising or retrieving strategy makes a call of its own. That work
        genuinely happens before the model does, so a failure in it genuinely
        belongs at call time rather than mid-stream.
        """
        return self._model.stream(await self._prompt(question, history))
