from fastapi import APIRouter

from shield_api.routers import audit, auth, chat, clearance, feedback, game, health, screening

api_router = APIRouter()
for module in (health, clearance, auth, screening, chat, feedback, audit, game):
    api_router.include_router(module.router)

__all__ = ["api_router"]
