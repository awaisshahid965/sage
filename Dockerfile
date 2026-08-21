# syntax=docker/dockerfile:1

# The uv image ships uv and a matching Python, so there is no pip bootstrap and
# no "which Python is this" question inside the container.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies get their own layer, ahead of the source. They change far less
# often, so editing a file in src/ reuses this layer instead of re-resolving
# the whole environment.
#
# README.md is here because pyproject names it as the project readme, and the
# build backend reads it when installing sage itself further down.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Ahead of everything, so `uvicorn` and `python` resolve to the project's venv
# without needing `uv run` at the front of every command.
ENV PATH="/app/.venv/bin:$PATH"

# Nothing in here needs root.
RUN useradd --create-home --uid 1000 sage && chown -R sage:sage /app
USER sage

EXPOSE 8000

# 0.0.0.0, not the 127.0.0.1 that `sage.config` defaults to: a container that
# binds loopback is unreachable from the host whatever the port mapping says.
CMD ["uvicorn", "sage.main:app", "--host", "0.0.0.0", "--port", "8000"]
