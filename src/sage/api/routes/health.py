"""Health and readiness endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from sage import __version__
from sage.api.schemas import HealthResponse
from sage.config import Settings, get_settings

router = APIRouter(tags=["system"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/health", summary="Liveness probe")
async def health(settings: SettingsDep) -> HealthResponse:
    """Report that the process is up and which build is serving."""
    return HealthResponse(version=__version__, environment=settings.environment)
