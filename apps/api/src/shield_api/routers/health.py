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
        moderation_enabled=container.shield.moderator is not None,
        adjudication_enabled=container.shield.adjudicator is not None,
        audit_backend=container.audit_log.backend,
    )
