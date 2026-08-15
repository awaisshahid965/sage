"""Show the distribution behind the first token of an answer.

    uv run poe logprobs "Do you ship to Berlin?"

Why this exists. It is easy to read that a language model "outputs a
probability distribution" and still picture it choosing a word. It does not.
At every step it scores every token it knows, normalises those scores into a
distribution, and samples one. This prints the top of that distribution for
the first step, so the claim becomes something you can look at.

Two things worth watching for:

- How lopsided it is. A confident model puts almost all the mass on one token.
- How the spread changes with the question. Ask something factual, then ask
  something open-ended, and compare.

Not every backend can do this, so the tool checks first and says so plainly.
`print` is the right output here, which is why this file is exempt from the
no-print lint rule in pyproject.toml.
"""

import asyncio
import sys

from sage.config import Settings, get_settings
from sage.domain.llm import (
    LLMError,
    Message,
    SupportsTokenChoices,
    TokenChoice,
)
from sage.llm.factory import create_chat_model

DEFAULT_QUESTION = "Do you ship to Berlin?"
BAR_WIDTH = 44


def render(question: str, settings: Settings, choices: list[TokenChoice]) -> str:
    """Build the report. Kept separate from printing so it can be tested."""
    lines = [
        "",
        f"  question : {question}",
        f"  backend  : {settings.llm_backend}",
        f"  model    : {settings.llm_model}",
        "",
        f"  top {len(choices)} candidates for the FIRST generated token",
        "",
    ]

    for rank, choice in enumerate(choices, start=1):
        percent = choice.probability * 100
        bar = "#" * round(choice.probability * BAR_WIDTH)
        # repr() so whitespace in the token is visible. Leading spaces are
        # part of the token for most tokenizers, and that surprises people.
        lines.append(f"  {rank}.  {choice.token!r:<16} {percent:>7.3f}%  {bar}")

    covered = sum(choice.probability for choice in choices) * 100
    lines += [
        "",
        f"  these {len(choices)} cover {covered:.2f}% of the probability mass",
        "",
    ]
    return "\n".join(lines)


async def run(question: str) -> int:
    """Return a process exit code."""
    settings = get_settings()
    model = create_chat_model(settings)

    # Ask before calling. `echo` has no distribution, so it never implements
    # this, and that is a normal answer rather than an error.
    if not isinstance(model, SupportsTokenChoices):
        print(
            f"\n  The {settings.llm_backend!r} backend cannot report "
            f"log-probabilities.\n  Try SAGE_LLM_BACKEND=langchain.\n"
        )
        return 1

    messages = [Message(role="user", content=question)]

    try:
        choices = await model.first_token_choices(messages, top_k=5)
    except LLMError as exc:
        print(f"\n  Could not read the distribution: {exc}\n")
        return 1

    print(render(question, settings, choices))
    return 0


def main() -> None:
    """Entry point. The question is everything after the command name."""
    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION
    sys.exit(asyncio.run(run(question)))


if __name__ == "__main__":
    main()
