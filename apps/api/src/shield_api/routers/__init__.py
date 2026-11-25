from fastapi import APIRouter

from shield_api.routers import account, auth, billing, clearance, game, health

api_router = APIRouter()
for module in (health, clearance, auth, account, billing, game):
    api_router.include_router(module.router)

__all__ = ["api_router"]
