from fastapi import APIRouter

from shield_api.dependencies import ContainerDep
from shield_api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(container: ContainerDep) -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service=container.settings.PROJECT_NAME,
        version=container.settings.VERSION,
        model_loaded=container.classifier is not None,
        agent_tiers=sorted(container.game_agents),
        storage_backend=container.scores.backend,
    )
