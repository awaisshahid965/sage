"""Reading the corpus off disk.

Not a port. There is one source of documents -- a directory of markdown -- and
inventing a `DocumentSource` protocol for it would be a seam with one side.
When documents start arriving from a CMS or an S3 bucket, this file is where
that abstraction earns its keep, and until then it is a function.
"""

from collections.abc import Sequence
from pathlib import Path

from sage.domain.retrieval import Document
from sage.logging import get_logger

log = get_logger(__name__)

# Two files in `data/pebble` are about the corpus rather than part of it, and
# one of them would quietly ruin every measurement taken against this system.
#
# `eval-questions.md` is the ground truth: every question, its correct answer,
# and the document it comes from, in one file. Index it and the retriever finds
# it for essentially any evaluation question — an answer key that matches the
# question wording far better than the policy document ever will. Recall goes
# up, the answers look excellent, and the numbers now measure nothing at all.
# The system would be reading the test paper.
#
# `README.md` is documentation about the corpus's design, including the list of
# deliberate traps. Harmless but not policy, and it would answer questions with
# commentary on the fixture instead of with the fixture.
EXCLUDED = frozenset({"README.md", "eval-questions.md"})


def load_documents(path: Path) -> Sequence[Document]:
    """Read every indexable markdown file under `path`, sorted by name.

    Sorted so an index build is reproducible: the same corpus produces chunks
    in the same order, so two builds differ only where the documents do.
    """
    if not path.is_dir():
        raise FileNotFoundError(f"No corpus directory at {path}.")

    documents: list[Document] = []

    for file in sorted(path.glob("*.md")):
        if file.name in EXCLUDED:
            log.debug("corpus_file_skipped", file=file.name)
            continue

        documents.append(
            Document(
                # Relative to the corpus root, so an index built on one machine
                # does not carry another machine's home directory in every
                # chunk's `source`.
                path=file.name,
                text=file.read_text(encoding="utf-8"),
            )
        )

    if not documents:
        raise FileNotFoundError(f"No indexable markdown files in {path}.")

    return documents
