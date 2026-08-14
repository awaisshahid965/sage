"""Shared FastAPI dependencies.

Routes ask for what they need instead of reaching into `app.state`, so a test
can swap the service with `app.dependency_overrides[get_sage] = ...`.
"""

from typing import Annotated

from fastapi import Depends, Request

from sage.application.chat import SageService


def get_sage(request: Request) -> SageService:
    """Return the service built once in `create_app`."""
    service: SageService = request.app.state.sage
    return service


SageDep = Annotated[SageService, Depends(get_sage)]
