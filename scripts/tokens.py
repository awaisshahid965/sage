"""Tokenizer playground. Deliberately NOT part of the app.

Nothing in src/sage imports this. It exists to be poked at and edited.

    uv run python scripts/tokens.py                 # the guided tour
    uv run python scripts/tokens.py "your text"     # split one string
    uv run python scripts/tokens.py --compare "hi"  # same text, two tokenizers

One caveat worth knowing: tiktoken is installed here as a side effect of
langchain-openai, not because this project asked for it. Fine for a
playground. If this ever moves into src/, declare it properly first with
`uv add tiktoken`, or it will vanish the day the dependency tree shifts.

The other caveat: tiktoken only knows OpenAI's tokenizers. A count from here
is an OpenAI count. Mistral and Llama chop differently, so these numbers are
the wrong ones for your Ollama runs. --compare shows how far apart two
tokenizers can be.
"""

import sys

import tiktoken

# Windows terminals default to a codepage that cannot print Arabic or CJK.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODEL = "gpt-4o-mini"


def split(text: str, model: str = MODEL) -> None:
    """Show every token in `text`: its position, its id, and its characters."""
    enc = tiktoken.encoding_for_model(model)
    ids = enc.encode(text)

    print(f"\n  text     {text!r}")
    print(f"  model    {model}  (encoding: {enc.name})")
    print(f"  tokens   {len(ids)}")
    print(f"  chars    {len(text)}  ->  {len(text) / len(ids):.2f} chars per token\n")

    print("     #        id  piece")
    print("     -        --  -----")
    for position, token_id in enumerate(ids):
        # decode one id on its own to see exactly what that token covers.
        # repr() so leading spaces are visible - they are part of the token.
        print(f"    {position:>2}  {token_id:>8}  {enc.decode([token_id])!r}")
    print()


def compare(text: str) -> None:
    """Same text, two OpenAI tokenizers, and whether they actually disagree.

    Reports what it measures rather than asserting a conclusion. The first
    version of this printed "they disagree" under two identical results,
    which is how you teach someone something false.
    """
    old = tiktoken.get_encoding("cl100k_base")  # gpt-4, gpt-3.5
    new = tiktoken.get_encoding("o200k_base")  # gpt-4o, gpt-4o-mini

    old_ids, new_ids = old.encode(text), new.encode(text)

    print(f"\n  text: {text!r}\n")
    print(f"  cl100k_base  {len(old_ids):>3} tokens   (gpt-4, gpt-3.5)")
    print(f"               {[old.decode([i]) for i in old_ids]}\n")
    print(f"  o200k_base   {len(new_ids):>3} tokens   (gpt-4o, gpt-4o-mini)")
    print(f"               {[new.decode([i]) for i in new_ids]}\n")

    if len(old_ids) == len(new_ids):
        print("  Same count. For plain English these two usually agree.")
        print("  Try again with non-Latin text to see them come apart.\n")
    else:
        ratio = len(old_ids) / len(new_ids)
        print(f"  Different: the older one needs {ratio:.1f}x more tokens.")
        print("  Two tokenizers from the SAME vendor, so the count you get")
        print("  depends on the model. Mistral and Llama differ again.\n")


def tour() -> None:
    """The cases that break people's mental model, with real numbers."""
    enc = tiktoken.encoding_for_model(MODEL)

    def row(text: str) -> None:
        ids = enc.encode(text)
        pieces = [enc.decode([i]) for i in ids]
        print(f"    {text!r:<36} {len(ids):>2}  {pieces}")

    sections = {
        "a space changes the token, it does not get stripped": [
            "hello",
            " hello",
        ],
        "capitals cost more": [
            "hello",
            "Hello",
            "HELLO",
        ],
        "common words are whole, rare words shatter": [
            " headphones",
            " Pebble",
            " antidisestablishmentarianism",
        ],
        "numbers split at arbitrary places (why models fumble arithmetic)": [
            " 30",
            " 2024",
            " PB-4471",
        ],
        "same meaning, different price": [
            "hello world",
            "你好世界",
            "مرحبا بالعالم",
        ],
        "your actual system prompt": [
            "You're a friendly support agent for Pebble, an online gadget store.",
        ],
    }

    for heading, samples in sections.items():
        print(f"\n  {heading}")
        print(f"    {'text':<36} {'n':>2}  pieces")
        for sample in samples:
            row(sample)
    print()


def main() -> None:
    args = sys.argv[1:]
    if not args:
        tour()
    elif args[0] == "--compare":
        compare(" ".join(args[1:]) or "مرحبا بالعالم")
    else:
        split(" ".join(args))


if __name__ == "__main__":
    main()
