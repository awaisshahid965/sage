"""Application entrypoint.

`app` is created at import time so `fastapi dev src/sage/main.py` and
`uvicorn sage.main:app` both find it, but the real construction lives in
`create_app()` so tests can build an isolated instance.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sage import __version__
from sage.api.router import api_router
from sage.config import Settings, get_settings
from sage.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the startup and shutdown of anything with a connection or a pool."""
    settings: Settings = app.state.settings
    log.info("starting", app=settings.app_name, environment=settings.environment)
    yield
    log.info("stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI instance. Pass `settings` to override the environment."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.include_router(api_router)

    # Routes depend on `get_settings`, which is cached process-wide. Point that
    # dependency at the instance this app was built with, so an app constructed
    # with explicit settings (tests, multi-tenant setups) really uses them.
    app.dependency_overrides[get_settings] = lambda: settings

    return app


app = create_app()
