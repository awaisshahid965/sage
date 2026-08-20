"""Tests for the context seam — the strategies, and the fact that it is a seam.

The two fakes below are deliberately the shapes of the techniques that have not
been written yet: `LastTurnOnly` is a one-turn sliding window, and `Passages` is
a retriever that returns text nobody said. If either needed a change to
`SageService` to work, the port would not be doing its job.
"""

from collections.abc import Sequence

from conftest import RecordingChatModel
from sage.application.chat import SYSTEM_PROMPT, SageService
from sage.context.combined import Combined
from sage.context.history import FullHistory
from sage.domain.context import Conversation
from sage.domain.llm import Message

TURNS = [
    Message(role="user", content="do you ship to Paris?"),
    Message(role="assistant", content="We do, in 3-5 days."),
]


class LastTurnOnly:
    """A sliding window of one. Selects fewer turns than it was given."""

    async def select(self, conversation: Conversation) -> Sequence[Message]:
        return conversation.history[-1:]


class Passages:
    """A retriever. Selects context that is not in the conversation at all."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def select(self, conversation: Conversation) -> Sequence[Message]:
        return [Message(role="system", content=f"Relevant policy: {self._text}")]


class RecordingStrategy:
    """Records the conversation it was asked about and selects nothing."""

    def __init__(self) -> None:
        self.seen: Conversation | None = None

    async def select(self, conversation: Conversation) -> Sequence[Message]:
        self.seen = conversation
        return ()


async def test_full_history_sends_every_turn() -> None:
    selected = await FullHistory().select(Conversation(question="q", history=TURNS))

    assert list(selected) == TURNS


async def test_full_history_on_a_fresh_conversation_selects_nothing() -> None:
    selected = await FullHistory().select(Conversation(question="q"))

    assert list(selected) == []


async def test_combined_concatenates_in_order() -> None:
    strategy = Combined(LastTurnOnly(), Passages("Returns close after 30 days."))

    selected = await strategy.select(Conversation(question="q", history=TURNS))

    assert [(m.role, m.content) for m in selected] == [
        ("assistant", "We do, in 3-5 days."),
        ("system", "Relevant policy: Returns close after 30 days."),
    ]


async def test_combined_with_nothing_in_it_selects_nothing() -> None:
    selected = await Combined().select(Conversation(question="q", history=TURNS))

    assert list(selected) == []


async def test_a_strategy_is_given_the_question_and_the_history_separately() -> None:
    """A retriever searches with the question; a window must not count it."""
    strategy = RecordingStrategy()

    await SageService(RecordingChatModel(), strategy).ask("and to Berlin?", TURNS)

    assert strategy.seen is not None
    assert strategy.seen.question == "and to Berlin?"
    assert list(strategy.seen.history) == TURNS


async def test_a_new_strategy_needs_no_change_to_the_service() -> None:
    """The reason the port exists.

    A window and a retriever, composed, dropped into a `SageService` that has
    never heard of either — and the frame around them is untouched:
    instructions first, live question last.
    """
    model = RecordingChatModel()
    service = SageService(model, Combined(LastTurnOnly(), Passages("30 days.")))

    await service.ask("and to Berlin?", TURNS)

    assert [(m.role, m.content) for m in model.seen] == [
        ("system", SYSTEM_PROMPT),
        ("assistant", "We do, in 3-5 days."),
        ("system", "Relevant policy: 30 days."),
        ("user", "and to Berlin?"),
    ]


async def test_the_strategy_shapes_the_streamed_prompt_too() -> None:
    """Both entry points share `_prompt`, so neither can drift from the other."""
    model = RecordingChatModel(reply="ok")
    service = SageService(model, LastTurnOnly())

    deltas = await service.ask_stream("and to Berlin?", TURNS)

    assert "".join([delta async for delta in deltas]) == "ok"
    assert [(m.role, m.content) for m in model.seen] == [
        ("system", SYSTEM_PROMPT),
        ("assistant", "We do, in 3-5 days."),
        ("user", "and to Berlin?"),
    ]
