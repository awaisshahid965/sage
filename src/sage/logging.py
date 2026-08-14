"""Structured logging setup.

Console-friendly and coloured while developing, line-delimited JSON in
production so a log shipper can parse it.
"""

import logging

import structlog


def configure_logging(*, level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog and route stdlib logging through it."""
    logging.basicConfig(format="%(message)s", level=getattr(logging, level))

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, conventionally named after the calling module."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
