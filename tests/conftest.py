"""Shared fixtures.

`conftest.py` is discovered automatically by pytest — no imports needed in the
test modules themselves.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from sage.config import Settings
from sage.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Settings for a test run, independent of the developer's `.env`."""
    return Settings(environment="test", log_level="WARNING")


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired straight to the ASGI app — no socket, no server."""
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
