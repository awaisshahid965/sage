# Sage

An AI assistant, and a playground for practising AI system design.

Built on **Python 3.12** + **FastAPI**, managed with **uv**.

## Requirements

- [uv](https://docs.astral.sh/uv/) — installs and manages Python itself, so it is the only prerequisite.

The Python version is pinned in [.python-version](.python-version) and enforced by
`requires-python` in [pyproject.toml](pyproject.toml). `uv` reads both and will
fetch the right interpreter automatically.

## Setup

```bash
uv sync                    # create .venv and install everything, from uv.lock
uv run pre-commit install  # install the git hooks
cp .env.example .env       # optional; every setting has a default
```

## Everyday commands

Tasks live under `[tool.poe.tasks]` in `pyproject.toml` — the equivalent of
`package.json` scripts.

| Command | What it does |
| --- | --- |
| `uv run poe dev` | Dev server with reload, on http://127.0.0.1:8000 |
| `uv run poe start` | Production server |
| `uv run poe lint` | Lint (ruff) |
| `uv run poe format` | Format (ruff) |
| `uv run poe typecheck` | Type check (mypy, strict) |
| `uv run poe test` | Tests (pytest) |
| `uv run poe test-cov` | Tests with a coverage report |
| `uv run poe fix` | Auto-fix formatting and lint |
| `uv run poe check` | Everything CI runs |

Interactive API docs are served at `/docs` outside production.

## Layout

```
src/sage/
  main.py          app factory + entrypoint
  config.py        typed settings from env / .env
  logging.py       structlog setup
  api/
    router.py      assembles the route modules
    schemas.py     request/response models
    routes/        one module per resource
tests/             mirrors src/, fixtures in conftest.py
docs/              setup guide
```

## Adding a dependency

```bash
uv add httpx           # runtime
uv add --dev pytest-mock   # tooling
```

Both update `pyproject.toml` and `uv.lock`, and install into `.venv`. Commit the
lockfile.

## Docs

- [docs/python-project-setup.md](docs/python-project-setup.md) — how this scaffold was
  built, step by step, mapped to the Node.js equivalents.
