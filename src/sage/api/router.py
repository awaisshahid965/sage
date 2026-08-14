"""The single router the app mounts, assembled from the route modules."""

from fastapi import APIRouter

from sage.api.routes import chat, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(chat.router)
