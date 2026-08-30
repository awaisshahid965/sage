"""Build the index.

    uv run poe index

Reads the same `Settings` the app does, so whatever `SAGE_EMBEDDING_BACKEND`
and `SAGE_VECTOR_STORE` say here is what the app will expect to find at
startup. That is the point of not giving this its own configuration: an indexer
that could be pointed somewhere the app is not is an indexer that will be.

`print` is the output, which is why this file is exempt from the no-print lint
rule in pyproject.toml.
"""

import asyncio
import sys

from sage.config import get_settings
from sage.domain.llm import LLMError
from sage.indexing.pipeline import IndexReport, build_index
from sage.logging import configure_logging


def render(report: IndexReport) -> str:
    return "\n".join(
        [
            "",
            f"  documents  : {report.documents}",
            f"  chunks     : {report.chunks}",
            f"  embedder   : {report.model_id}",
            f"  dimensions : {report.dimensions}",
            f"  chunker    : {report.chunker}",
            f"  store      : {report.store}",
            "",
        ]
    )


async def run() -> int:
    """Return a process exit code."""
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    try:
        report = await build_index(settings)
    except FileNotFoundError as exc:
        print(f"\n  Nothing to index: {exc}\n")
        return 1
    except LLMError as exc:
        # The embedding provider refused or could not be reached. A failed
        # build leaves the previous index alone — nothing has been written.
        print(f"\n  The embedder failed: {exc}\n")
        return 1

    print(render(report))
    return 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
