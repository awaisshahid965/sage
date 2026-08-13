# Setting up a Python project, for someone who does this blindfolded in Node.js

This is the complete build log for the scaffold in this repo: every step, why the
tool was chosen, and the things that bit along the way. It assumes you know the
Node.js equivalents cold and just need the mapping.

## The mapping, at a glance

| Node.js | Python | Notes |
| --- | --- | --- |
| `npm` / `pnpm` | **uv** | Also installs Python itself. Astral, Rust, very fast. |
| `package.json` | `pyproject.toml` | One file, standardised (PEP 621). |
| `package-lock.json` | `uv.lock` | Commit it. Cross-platform by design. |
| `npm ci` | `uv sync --locked` | Fails on a stale lockfile instead of re-resolving. |
| `node_modules/` | `.venv/` | Gitignored. `uv run` activates it implicitly. |
| `engines.node` | `requires-python` + `.python-version` | See [Pinning the version](#3-pinning-the-python-version). |
| `dependencies` | `[project] dependencies` | |
| `devDependencies` | `[dependency-groups] dev` | PEP 735. Not shipped to consumers. |
| ESLint | **Ruff** (`ruff check`) | |
| Prettier | **Ruff** (`ruff format`) | Same binary as the linter. |
| `tsc --noEmit` | **mypy** | Types are optional in Python; strict mode makes them not. |
| Jest / Vitest | **pytest** | |
| husky + lint-staged | **pre-commit** | One tool, both jobs. |
| Express / Nest | **FastAPI** | |
| `scripts` | `[tool.poe.tasks]` | Via `poethepoet`; `pyproject.toml` has no native scripts table. |

The headline difference: in Node you assemble ten packages. In Python, **Ruff
replaces both ESLint and Prettier** — one binary, one config block, no
eslint-config-prettier dance to stop them disagreeing.

---

## 1. Install uv

uv is the only thing you install globally. It manages Python interpreters,
virtualenvs, dependencies and lockfiles.

```powershell
# Windows
irm https://astral.sh/uv/install.ps1 | iex
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
uv --version   # uv 0.11.8
```

## 2. Check what Python you have

```powershell
python --version   # Python 3.12.9
uv python list     # everything installed + everything downloadable
```

This project targets the **3.12.9** already on the machine. If you had wanted a
different one, uv fetches it — no pyenv, no system package manager:

```powershell
uv python install 3.13
```

## 3. Pinning the Python version

This is `engines.node`, except it's split across two files that do different
jobs — and unlike `engines`, both are actually enforced.

```powershell
uv python pin 3.12   # writes .python-version
```

**`.python-version`** — the version *this checkout uses*. uv reads it on every
command and selects (or downloads) that interpreter. Commit it.

**`requires-python`** in `pyproject.toml` — the range the *code supports*. It
feeds dependency resolution: uv will refuse a package that doesn't support your
floor.

```toml
requires-python = ">=3.12,<3.13"
```

The upper bound is a deliberate choice, not boilerplate. `>=3.12` alone tells uv
to resolve dependencies that work on 3.13, 3.14 and every future version, which
rules out packages that haven't declared support yet. Since this project pins one
version anyway, capping the range keeps resolution honest. If you later want to
support a span of versions, widen it and test the whole matrix in CI.

`target-version` under `[tool.ruff]` and `python_version` under `[tool.mypy]`
should agree with this. Three places, one number.

## 4. Create the project

The layout matters more in Python than in Node:

```
src/sage/       <- the package
tests/
pyproject.toml
```

This is the **src layout**. The alternative — package directory at the repo root
— means your tests import the *source folder* rather than the *installed
package*, so packaging bugs (a missing `__init__.py`, a file that never made it
into the wheel) don't surface until someone installs it for real. src layout
makes tests import the same artifact your users get. Use it.

Every directory in the package needs an `__init__.py`. It marks the directory as
a package; there's no `index.js` convention doing this implicitly.

## 5. pyproject.toml

One file for metadata, dependencies, and *every tool's config* — imagine
`package.json`, `.eslintrc`, `.prettierrc`, `tsconfig.json` and `jest.config.js`
merged, which is genuinely nicer.

```toml
[project]
name = "sage"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi[standard]>=0.121.0",
    ...
]

[dependency-groups]
dev = ["ruff>=0.15.0", "mypy>=1.19.0", "pytest>=9.0.0", ...]
```

`fastapi[standard]` — the bracket is an **extra**, an optional feature bundle
declared by the package. `standard` pulls in uvicorn, the `fastapi` CLI, httpx
and the rest of the batteries. Roughly a meta-package, but versioned as one unit.

### Version specifiers

`>=0.121.0` is the Python idiom, and it is *not* npm's `^0.121.0`. Python has no
caret. A bare `>=` allows any future major version — which is fine here, because
`uv.lock` is what actually determines installed versions. The floor documents the
minimum you rely on; the lockfile guarantees reproducibility. Only add an upper
bound when you know a future major will break you.

### The build backend

```toml
[build-system]
requires = ["uv_build>=0.11.0,<0.12.0"]
build-backend = "uv_build"
```

This exists because the project installs *itself* into the venv (as an editable
install), which is what lets tests do `from sage.main import create_app` from
anywhere without path hacks. Node has no equivalent — there's nothing to build to
make `require('./src')` work.

## 6. Install

```powershell
uv sync
```

Creates `.venv/`, resolves everything, writes `uv.lock`, installs the project
itself in editable mode. The one command that replaces `npm install`.

Run things with `uv run <cmd>` — no manual `source .venv/bin/activate`. `uv run`
also re-syncs if `pyproject.toml` changed, so the venv can't silently drift.

Adding dependencies later:

```powershell
uv add httpx                # runtime
uv add --dev pytest-mock    # dev group
uv remove httpx
```

## 7. Ruff — linter and formatter

```toml
[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "A", "C4", "DTZ", "T20", "SIM", "TC", "PTH", "RUF"]
ignore = ["E501"]
```

Ruff ships hundreds of rules ported from the old flake8-plugin ecosystem, all
off by default. You opt in by prefix. The set above is a solid default:

- **`F`** — pyflakes. Undefined names, unused imports. The `no-undef` /
  `no-unused-vars` tier, and the one that catches real bugs.
- **`I`** — import sorting. This is `isort` built in; no separate tool.
- **`UP`** — pyupgrade. Rewrites old syntax to the modern equivalent for your
  `target-version`. Free modernisation on every save.
- **`B`** — bugbear. Genuine footguns, above all mutable default arguments.
- **`DTZ`** — bans naive `datetime.now()`. Timezone bugs are the ones that reach
  production, and this rule alone justifies the list.
- **`T20`** — no stray `print()`. The `no-console` equivalent.
- **`PTH`** — prefer `pathlib` over `os.path`.
- **`TC`** — pushes type-only imports into `if TYPE_CHECKING:` blocks, keeping
  them out of runtime.

`E501` (line length) is ignored deliberately: the formatter owns line width, and
leaving the lint rule on means being told about lines the formatter has already
decided it cannot split.

```powershell
uv run ruff check src tests      # lint
uv run ruff check --fix src tests
uv run ruff format src tests     # format
```

Ruff is near-instant, so unlike ESLint on a big repo there's no reason not to run
it on everything every time.

## 8. mypy — the type checker

Python's types are annotations that do nothing at runtime; a checker gives them
teeth.

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
plugins = ["pydantic.mypy"]
```

`strict = true` is the important line, and it is the single biggest lever in the
whole config. Without it mypy silently treats every unannotated function as
`Any`, and you get a type checker that agrees with everything — the equivalent of
TypeScript with `strict: false` *and* `checkJs` off. Turn it on from day one on a
new project; retrofitting it later is the painful path.

The `pydantic.mypy` plugin teaches mypy how pydantic generates `__init__` from
model fields, so wrong constructor arguments get caught.

Tests relax one rule (`disallow_untyped_defs = false`) via an override — test
functions taking fixtures by name don't benefit from annotations.

```powershell
uv run mypy src tests
```

## 9. pytest

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers --strict-config"
asyncio_mode = "auto"
filterwarnings = ["error"]
```

- **`asyncio_mode = "auto"`** — `async def test_*` just works, no decorator on
  every test.
- **`filterwarnings = ["error"]`** — promotes warnings to failures. This is how
  you find out about a deprecation while it's still a deprecation.
- **`--strict-markers` / `--strict-config`** — typo'd marker or config key is an
  error, not a silent no-op.

### Fixtures instead of `beforeEach`

`conftest.py` is auto-discovered — fixtures defined there are available to every
test in the directory tree, with no import. A test requests a fixture by naming
it as a parameter:

```python
@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Anything before `yield` is setup, anything after is teardown. Fixtures compose —
`client` requests `settings`, which pytest resolves first.

`ASGITransport` wires httpx directly to the ASGI app: no socket, no port, no
server process. Tests run in milliseconds.

## 10. Task runner

`pyproject.toml` has no `scripts` table. `poethepoet` adds one:

```toml
[tool.poe.tasks]
dev = "fastapi dev src/sage/main.py"
lint = "ruff check src tests"
typecheck = "mypy src tests"
test = "pytest"

[tool.poe.tasks.check]
sequence = ["format-check", "lint", "typecheck", "test"]
```

```powershell
uv run poe dev
uv run poe check
```

A `Makefile` is the common alternative, but `make` isn't on Windows by default —
`poe` is just another dev dependency and works everywhere.

## 11. pre-commit — husky + lint-staged in one

`.pre-commit-config.yaml`:

```yaml
default_install_hook_types: [pre-commit, pre-push]

repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.22
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
```

```powershell
uv run pre-commit install        # once per clone — writes .git/hooks/
uv run pre-commit run --all-files
uv run pre-commit autoupdate     # bump the pinned revs
```

Two things differ from husky:

**Hooks run only on staged files, automatically.** That's lint-staged's whole job,
built in. No configuration.

**Most hooks run in their own isolated environment**, pinned by git tag (`rev:`),
not from your venv. Reproducible across machines, and CI doesn't depend on
whatever the developer happened to have installed.

That isolation is wrong for type checking, though — mypy in a bare environment
can't see FastAPI's or pydantic's type stubs, so it would report errors that
don't exist. Those hooks use `language: system` to run from the project venv:

```yaml
  - repo: local
    hooks:
      - id: mypy
        entry: uv run mypy src tests
        language: system
        types: [python]
        pass_filenames: false
```

`pass_filenames: false` matters: mypy needs the whole package to resolve imports,
not just the files you touched.

Tests are on `stages: [pre-push]` — fast checks gate the commit, the slower suite
gates the push.

## 12. CI

`.github/workflows/ci.yml` runs the same gates in the same order:

```yaml
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv python install          # reads .python-version
      - run: uv sync --locked --all-groups
```

`--locked` is the `npm ci` equivalent — it **fails** if `uv.lock` disagrees with
`pyproject.toml`, rather than quietly resolving something new. Without it, CI can
pass against dependencies nobody has ever run locally.

---

## Things that bit, and what they teach

Recording these because each one cost real time.

**`pytest-cov>=8.0.0` didn't resolve.** I guessed a version that doesn't exist —
the latest is 7.1.0. uv's error is precise (`only pytest-cov<=7.1.0 is
available`). Don't guess version floors; run `uv add <pkg>` and let it write the
current one.

**The build failed on a missing `README.md`.** `readme = "README.md"` in
`pyproject.toml` is a hard reference — the build backend reads that file to embed
as package metadata. Declaring it means it must exist.

**`create_app(settings)` didn't actually use the settings passed in.** This one
was a genuine bug, caught by the first test run. The route resolved settings
through `Depends(get_settings)`, and `get_settings` is `@lru_cache`d — so it
returned the cached global and ignored the argument entirely. The fix:

```python
app.dependency_overrides[get_settings] = lambda: settings
```

The lesson generalises: with FastAPI's DI, *what you inject is decided by the
dependency callable, not by the object you happen to hold*. A cached provider
silently outranks a constructor argument. `dependency_overrides` is the seam —
the same one you'd use to swap a database or an LLM client for a fake.

**`mixed-line-ending --fix=lf` fought git.** `.gitattributes` has `* text=auto`,
so git keeps LF in the repo and CRLF in the Windows working copy. A hook that
rewrites the working copy to LF undoes that on every commit, forever. Removed the
hook — `.gitattributes` already does this job correctly, at the right layer.

**The mypy hook ran with no arguments.** `entry: uv run mypy` plus
`pass_filenames: false` means mypy is invoked with nothing to check. Needs the
targets spelled out: `entry: uv run mypy src tests`.

---

## Reproducing this from scratch

```powershell
uv init --package --name sage          # scaffold pyproject.toml + src layout
uv python pin 3.12                     # write .python-version
uv add "fastapi[standard]" pydantic-settings structlog
uv add --dev ruff mypy pytest pytest-asyncio pytest-cov pre-commit poethepoet
# ...configure [tool.ruff] / [tool.mypy] / [tool.pytest.ini_options] / [tool.poe.tasks]
# ...write .pre-commit-config.yaml
uv run pre-commit install
uv run pre-commit autoupdate           # pin hook revs to real releases
uv run poe check                       # verify the whole gate passes
```

## Reference

- [uv](https://docs.astral.sh/uv/)
- [Ruff rules](https://docs.astral.sh/ruff/rules/)
- [mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html)
- [pytest fixtures](https://docs.pytest.org/en/stable/explanation/fixtures.html)
- [pre-commit](https://pre-commit.com/)
- [FastAPI](https://fastapi.tiangolo.com/)
