"""Application entrypoint.

`app` is created at import time so `fastapi dev src/sage/main.py` and
`uvicorn sage.main:app` both find it, but the real construction lives in
`create_app()` so tests can build an isolated instance.

This is the only file that knows how the layers are wired together. It picks a
backend, wraps it in the service, and hands the service to the routes.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sage import __version__
from sage.api.router import api_router
from sage.api.schemas import ErrorResponse
from sage.application.chat import (
    RETRIEVAL_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    SageService,
)
from sage.config import Settings, get_settings
from sage.context.combined import Combined
from sage.context.history import FullHistory
from sage.context.passages import Passages
from sage.conversations.factory import create_conversation_store
from sage.domain.context import ContextStrategy
from sage.domain.llm import LLMError
from sage.domain.retrieval import Embedder, VectorStore
from sage.embeddings.factory import create_embedder
from sage.llm.factory import create_chat_model
from sage.logging import configure_logging, get_logger
from sage.retrieval.dense import DenseRetriever
from sage.retrieval.guard import verify_index
from sage.vectorstores.factory import create_vector_store

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the startup and shutdown of anything with a connection or a pool."""
    settings: Settings = app.state.settings
    log.info(
        "starting",
        app=settings.app_name,
        environment=settings.environment,
        llm_backend=settings.llm_backend,
        retrieval=settings.retrieval,
    )

    # Here and not in `create_app` because it is the first piece of startup
    # that needs I/O, and `create_app` is synchronous. Failing here still fails
    # the process before it serves a request, which is the property that
    # matters: a stale index is refused rather than quietly answered from.
    if settings.retrieval:
        await verify_index(app.state.vector_store, app.state.embedder)

    yield
    log.info("stopped")


async def handle_llm_error(request: Request, exc: Exception) -> JSONResponse:
    """Turn any backend failure into a 502.

    Every adapter raises `LLMError`, so this one handler covers all of them and
    no provider detail reaches the client.
    """
    log.error("llm_call_failed", error=str(exc))
    body = ErrorResponse(detail="The language model could not be reached.")
    return JSONResponse(status_code=502, content=body.model_dump())


def _build_context(
    settings: Settings,
) -> tuple[ContextStrategy, Embedder | None, VectorStore | None]:
    """Assemble the context strategy, and whatever retrieval needed to exist.

    Returns the embedder and store alongside, rather than hiding them inside
    the strategy, because `lifespan` has to check the index against the
    embedder and there is no way back out through a `ContextStrategy` -- the
    port deliberately exposes nothing but `select`.

    `None` when retrieval is off, which is the whole of the difference: no
    embedder is built, no index is opened, and nothing needs to exist on disk.
    """
    if not settings.retrieval:
        return FullHistory(), None, None

    embedder = create_embedder(settings)
    store = create_vector_store(settings)
    retriever = DenseRetriever(embedder, store, top_k=settings.retrieval_top_k)

    # Order is the order they reach the model in: the conversation so far,
    # then the reference material, then the live question that `SageService`
    # appends. Passages sit next to the question they were retrieved for.
    return Combined(FullHistory(), Passages(retriever)), embedder, store


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI instance. Pass `settings` to override the environment."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    # Built once, at startup, so a bad model name or a missing key fails here
    # rather than on the first request.
    #
    # Three arguments, three ports: who answers, what they are told, what is
    # remembered. The middle one is where a sliding window, a summariser, or
    # retrieval goes -- on its own or inside a `Combined(...)`.
    #
    # This is the promise that file made being kept. Retrieval is four new
    # classes and a config flag, and the only thing that moved above the ports
    # is which strategy gets passed here.
    context, embedder, store = _build_context(settings)

    sage = SageService(
        create_chat_model(settings),
        context,
        create_conversation_store(settings),
        system_prompt=RETRIEVAL_SYSTEM_PROMPT if settings.retrieval else SYSTEM_PROMPT,
    )

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.sage = sage
    # Kept for `lifespan`, which needs both to run the staleness check and
    # cannot reach inside the service to find them.
    app.state.embedder = embedder
    app.state.vector_store = store
    app.include_router(api_router)
    app.add_exception_handler(LLMError, handle_llm_error)

    # Routes depend on `get_settings`, which is cached process-wide. Point that
    # dependency at the instance this app was built with, so an app constructed
    # with explicit settings (tests, multi-tenant setups) really uses them.
    app.dependency_overrides[get_settings] = lambda: settings

    return app


app = create_app()
