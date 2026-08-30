"""Chunking on markdown headings.

The corpus is structured documentation: front matter, one `#` title, numbered
`##` sections, occasional `###` subsections. Sections are self-contained and
already numbered for citation, so the document's own structure is a better
chunk boundary than any window a tokeniser could pick -- and it is free.

Two things this does that a naive splitter does not.

**Tables are atomic.** Splitting a table mid-row produces chunks where the
header is gone and `| 14 days |` is a number attached to nothing. Once that
chunk is retrieved, the model has no way to know what the number measures. A
contiguous run of `|` lines is therefore treated as one indivisible block, even
if that leaves a chunk over the size limit -- an oversized chunk costs tokens,
a decapitated table costs correctness.

**Every chunk starts with a breadcrumb.** See `Chunk` in the domain module for
why. It is the mechanism that replaces overlap: the usual reason to repeat text
across chunk boundaries is that a fragment read alone has lost its context, and
naming the document and section restores more of that than a duplicated
paragraph does, without inflating the index or returning the same passage twice
under two ids. If evals later show answers falling in the gaps between
sections, overlap is the knob to add -- with a measurement behind it.
"""

import re
from collections.abc import Iterator, Sequence
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from sage.domain.retrieval import Chunk, Document

# Chunk ids have to be stable across runs so that re-indexing an unchanged
# corpus produces an unchanged index, and a diff of two index builds shows only
# what actually moved. uuid5 is a hash, not a random draw, so the same inputs
# always give the same id.
_ID_NAMESPACE = uuid5(NAMESPACE_URL, "https://sage.invalid/chunk")

# `## 2. Category exceptions` -> level 2, "2. Category exceptions"
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# The leading number of a heading, which is what a citation uses. `## 1.
# Headphones` -> "1". A heading with no number falls back to its own text.
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")

# Roughly 450 tokens at the usual four-characters-a-token rule of thumb. Most
# sections in this corpus come in well under it and stay whole, which is the
# intended outcome -- the limit is a backstop for the few that do not, not the
# primary mechanism.
DEFAULT_MAX_CHARS = 1800


class HeadingChunker:
    """Splits markdown into one chunk per section, with a size backstop."""

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS) -> None:
        self._max_chars = max_chars

    @property
    def name(self) -> str:
        return f"heading:{self._max_chars}"

    def split(self, document: Document) -> Sequence[Chunk]:
        front_matter, body = _split_front_matter(document.text)

        doc_id = front_matter.get("doc_id", document.path)
        # Front matter first, then the document's own `#` heading, then the
        # filename. The middle one matters: a document with no front matter
        # still says what it is on its first line, and falling straight through
        # to "04-product-catalogue.md" would put that in every breadcrumb --
        # embedded, retrieved, and shown to the model as the document's name.
        title = front_matter.get("title") or _first_heading(body) or doc_id
        version = front_matter.get("version", "0")
        effective_from = _parse_date(front_matter.get("effective_from"))

        chunks: list[Chunk] = []

        for section in _sections(body):
            for text in _within_size(section.body, self._max_chars):
                ordinal = len(chunks)
                heading = section.heading
                breadcrumb = f"{title} ({doc_id} v{version}) > {heading}"

                chunks.append(
                    Chunk(
                        id=str(uuid5(_ID_NAMESPACE, f"{doc_id}|{heading}|{ordinal}")),
                        text=f"{breadcrumb}\n\n{text}",
                        doc_id=doc_id,
                        title=title,
                        version=version,
                        section=section.number,
                        heading=heading,
                        ordinal=ordinal,
                        source=document.path,
                        effective_from=effective_from,
                    )
                )

        return chunks


class _Section:
    """One heading's worth of document, before the size limit is applied."""

    __slots__ = ("body", "heading", "number")

    def __init__(self, number: str, heading: str, body: str) -> None:
        self.number = number
        self.heading = heading
        self.body = body


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Peel off a leading `---` block, returning its fields and the rest.

    Hand-parsed rather than pulled through a YAML library, because the front
    matter here is flat `key: value` lines and adding a dependency to read ten
    of them is a poor trade. A document that grows nested front matter will
    break this loudly -- values simply come back as strings -- which is the
    right time to reach for the real parser.

    Only a `---` on the very first line opens a block. Horizontal rules appear
    mid-document in this corpus, and treating one of those as a delimiter would
    silently swallow half a file.
    """
    if not text.startswith("---\n"):
        return {}, text

    closing = text.find("\n---\n", 3)
    if closing == -1:
        return {}, text

    fields: dict[str, str] = {}
    for line in text[4:closing].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()

    return fields, text[closing + 5 :]


def _first_heading(body: str) -> str | None:
    """The text of the document's `#` title, if it has one."""
    for line in body.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2)
    return None


def _parse_date(value: str | None) -> date | None:
    """Read an ISO date, tolerating a missing or malformed one.

    Metadata being absent is not a reason to refuse to index a document. The
    field is optional on `Chunk` for the same reason.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _sections(body: str) -> Iterator[_Section]:
    """Walk the body, yielding a section per `##` and per `###`.

    The `#` title is not a boundary -- it names the document, which the
    breadcrumb already carries. Text between the title and the first `##` is
    yielded as a preamble section, because in this corpus that is where a
    document says what it governs and which other document takes over where it
    stops. That is genuinely retrievable content, and dropping it would lose
    the cross-references entirely.

    A `##` that has `###` children *and* its own text before the first of them
    yields both: the intro as its own chunk, then one per child. The
    alternative is attaching the intro to the first child, which makes that
    child's chunk mean something different from its siblings'.
    """
    number = "0"
    heading = "Preamble"
    lines: list[str] = []
    in_code_fence = False

    for line in body.splitlines():
        # A `#` inside a fenced code block is not a heading. Cheap to honour
        # and the alternative is a chunker that can be confused by a shell
        # comment in an example.
        if line.startswith("```"):
            in_code_fence = not in_code_fence

        match = None if in_code_fence else _HEADING.match(line)

        if match is None:
            lines.append(line)
            continue

        hashes, text = match.groups()
        level = len(hashes)

        if level == 1:
            # The document title. Not a boundary, and not body text either.
            continue

        if _has_content(lines):
            yield _Section(number, heading, _tidy(lines))

        lines = []

        if level == 2:
            number = _section_number(text)
            heading = text
        else:
            # A subsection keeps its parent's citation number -- "§1" is what
            # the document itself offers as an anchor, and inventing "§1.2"
            # would cite something that is not written anywhere.
            heading = f"{_parent(heading)} > {text}"

    if _has_content(lines):
        yield _Section(number, heading, _tidy(lines))


def _parent(heading: str) -> str:
    """The `##` part of a heading path, dropping any `###` already on it."""
    return heading.split(" > ", 1)[0]


def _section_number(text: str) -> str:
    match = _SECTION_NUMBER.match(text)
    return match.group(1) if match else text


def _has_content(lines: list[str]) -> bool:
    return any(line.strip() for line in lines)


def _tidy(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def _within_size(body: str, max_chars: int) -> Iterator[str]:
    """Yield `body` whole, or in pieces if it is over the limit.

    Pieces break on blank lines, so a paragraph is never cut in half, and a run
    of table rows counts as a single paragraph however long it is. A table that
    exceeds the limit on its own is yielded oversized and intact.
    """
    if len(body) <= max_chars:
        yield body
        return

    piece: list[str] = []
    length = 0

    for block in _blocks(body):
        # `+ 2` for the blank line that will rejoin them.
        if piece and length + len(block) + 2 > max_chars:
            yield "\n\n".join(piece)
            piece = []
            length = 0

        piece.append(block)
        length += len(block) + 2

    if piece:
        yield "\n\n".join(piece)


def _blocks(body: str) -> Iterator[str]:
    """Split on blank lines, keeping contiguous table rows together.

    Markdown allows no blank line inside a table, so a table is already one
    blank-line-delimited block. This function exists to make that a stated
    guarantee rather than an accident of the syntax -- and to keep a table
    joined to the row above it if a document ever puts a stray blank line in
    the middle of one.
    """
    current: list[str] = []

    for raw in body.split("\n\n"):
        block = raw.strip()
        if not block:
            continue

        if current and _is_table(block) and _is_table(current[-1]):
            current[-1] = f"{current[-1]}\n{block}"
            continue

        current.append(block)

    yield from current


def _is_table(block: str) -> bool:
    return block.lstrip().startswith("|")
