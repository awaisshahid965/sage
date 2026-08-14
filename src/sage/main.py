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
from sage.application.chat import SageService
from sage.config import Settings, get_settings
from sage.domain.llm import LLMError
from sage.llm.factory import create_chat_model
from sage.logging import configure_logging, get_logger

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
    )
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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI instance. Pass `settings` to override the environment."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    # Built once, at startup, so a bad model name or a missing key fails here
    # rather than on the first request.
    sage = SageService(create_chat_model(settings))

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
    app.include_router(api_router)
    app.add_exception_handler(LLMError, handle_llm_error)

    # Routes depend on `get_settings`, which is cached process-wide. Point that
    # dependency at the instance this app was built with, so an app constructed
    # with explicit settings (tests, multi-tenant setups) really uses them.
    app.dependency_overrides[get_settings] = lambda: settings

    return app


app = create_app()
