"""Tests for the chunker, including against the real corpus.

Most of these are unit tests over small hand-written documents, which is the
right default. The last two are not: they run over `data/pebble` itself,
because the properties they check -- tables surviving intact, every chunk
carrying a citable document id -- are properties of this chunker meeting these
documents, and a fixture that stayed passing while the corpus changed would be
measuring nothing.
"""

from pathlib import Path

from sage.chunking.markdown import HeadingChunker
from sage.domain.retrieval import Document
from sage.indexing.corpus import EXCLUDED, load_documents

CORPUS = Path("data/pebble")

DOC = Document(
    path="policy.md",
    text="""---
doc_id: POL-TEST-001
title: Test Policy
version: 2.1
effective_from: 2025-01-15
---

# Test Policy

This policy governs testing. It defers to POL-OTHER-002.

## 1. First section

The general rule is thirty days.

## 2. Second section

| Category | Window |
| --- | --- |
| Sealed | 30 days |
| Opened | 14 days |

The exception is the interesting one.

## 3. Third section

### A subsection

Details about the subsection.

### Another subsection

More details.
""",
)


def test_front_matter_becomes_metadata_not_text() -> None:
    chunks = HeadingChunker().split(DOC)

    assert all(chunk.doc_id == "POL-TEST-001" for chunk in chunks)
    assert all(chunk.version == "2.1" for chunk in chunks)
    assert all("doc_id:" not in chunk.text for chunk in chunks)


def test_effective_date_is_parsed() -> None:
    chunk = HeadingChunker().split(DOC)[0]

    assert chunk.effective_from is not None
    assert chunk.effective_from.isoformat() == "2025-01-15"


def test_every_chunk_opens_with_its_breadcrumb() -> None:
    """The mechanism the whole design leans on. Without it a retrieved table
    row is a number attached to nothing."""
    for chunk in HeadingChunker().split(DOC):
        first_line = chunk.text.splitlines()[0]

        assert first_line.startswith("Test Policy (POL-TEST-001 v2.1) > ")
        assert chunk.heading in first_line


def test_the_preamble_is_kept() -> None:
    """It is where a document says which other document takes over, and those
    cross-references are unrecoverable if it is dropped."""
    preamble = HeadingChunker().split(DOC)[0]

    assert preamble.section == "0"
    assert "POL-OTHER-002" in preamble.text


def test_sections_split_on_headings() -> None:
    sections = [chunk.section for chunk in HeadingChunker().split(DOC)]

    assert sections == ["0", "1", "2", "3", "3"]


def test_a_subsection_keeps_its_parents_citation_number() -> None:
    """ "§3" is an anchor the document actually offers. "§3.1" is invented."""
    chunks = [c for c in HeadingChunker().split(DOC) if "subsection" in c.heading]

    assert [chunk.section for chunk in chunks] == ["3", "3"]
    assert chunks[0].heading == "3. Third section > A subsection"
    assert chunks[1].heading == "3. Third section > Another subsection"


def test_citation_names_a_document_and_a_section() -> None:
    chunk = HeadingChunker().split(DOC)[1]

    assert chunk.citation == "POL-TEST-001 v2.1 §1"


def test_ids_are_stable_across_runs() -> None:
    """Re-indexing an unchanged corpus must produce an unchanged index."""
    first = [chunk.id for chunk in HeadingChunker().split(DOC)]
    second = [chunk.id for chunk in HeadingChunker().split(DOC)]

    assert first == second
    assert len(set(first)) == len(first)


def test_a_horizontal_rule_is_not_front_matter() -> None:
    """`---` mid-document is a rule. Only line one opens a block, and treating
    a rule as a delimiter would swallow everything above it."""
    document = Document(
        path="x.md", text="# Title\n\n## 1. One\n\nBefore\n\n---\n\nAfter\n"
    )

    chunks = HeadingChunker().split(document)

    assert chunks[0].doc_id == "x.md"
    assert "After" in chunks[0].text


def test_an_oversized_section_splits_on_paragraphs() -> None:
    body = "\n\n".join(
        f"Paragraph number {n} with some filler text." * 3 for n in range(20)
    )
    document = Document(path="x.md", text=f"# T\n\n## 1. Big\n\n{body}\n")

    chunks = HeadingChunker(max_chars=400).split(document)

    assert len(chunks) > 1
    # Every piece still says where it came from, so a fragment retrieved alone
    # is still attributable.
    assert all(chunk.section == "1" for chunk in chunks)
    assert all(chunk.text.startswith("T (x.md v0) > 1. Big") for chunk in chunks)


def test_a_table_is_never_split_even_when_oversized() -> None:
    """The failure this exists to prevent: a chunk of numbers with no header,
    where "14 days" is unattributable to anything."""
    rows = "\n".join(
        f"| Category {n} | {n} days | Some note about it |" for n in range(40)
    )
    table = f"| Category | Window | Notes |\n| --- | --- | --- |\n{rows}"
    document = Document(path="x.md", text=f"# T\n\n## 1. Table\n\n{table}\n")

    chunks = HeadingChunker(max_chars=200).split(document)

    holding_rows = [chunk for chunk in chunks if "| Category 39 |" in chunk.text]

    assert len(holding_rows) == 1
    assert "| Category | Window | Notes |" in holding_rows[0].text


def test_the_real_corpus_keeps_its_tables_whole() -> None:
    chunker = HeadingChunker()

    for document in load_documents(CORPUS):
        for chunk in chunker.split(document):
            rows = [
                line
                for line in chunk.text.splitlines()
                if line.lstrip().startswith("|")
            ]
            if not rows:
                continue

            # A table that made it into a chunk brought its header with it. The
            # separator row is the marker that a header is present.
            assert any(
                set(row.replace("|", "").strip()) <= {"-", " ", ":"} for row in rows
            ), f"{chunk.citation} has table rows with no header row"


def test_the_real_corpus_is_fully_citable() -> None:
    chunker = HeadingChunker()

    for document in load_documents(CORPUS):
        chunks = chunker.split(document)

        assert chunks, f"{document.path} produced no chunks"
        for chunk in chunks:
            assert chunk.doc_id.startswith(("POL-", "CAT-")), chunk.doc_id
            assert chunk.version
            assert chunk.effective_from is not None


def test_the_answer_key_is_not_indexable() -> None:
    """`eval-questions.md` holds every question with its answer and source. In
    the index it would out-match the policy documents on essentially every
    evaluation question, and the resulting scores would measure nothing."""
    assert "eval-questions.md" in EXCLUDED

    loaded = {document.path for document in load_documents(CORPUS)}

    assert "eval-questions.md" not in loaded
    assert "README.md" not in loaded
    assert len(loaded) == 8
