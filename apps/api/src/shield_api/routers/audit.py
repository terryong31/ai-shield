from typing import Annotated

from fastapi import APIRouter, Query

from shield_api.dependencies import ContainerDep
from shield_api.schemas import AuditRecord, StatsResponse

router = APIRouter(tags=["Audit"])


@router.get("/requests")
async def list_requests(
    container: ContainerDep, limit: Annotated[int, Query(ge=1, le=200)] = 30
) -> list[AuditRecord]:
    """Recent screened requests, newest first."""
    return await container.audit_log.recent(limit)


@router.get("/stats")
async def stats(container: ContainerDep) -> StatsResponse:
    return await container.audit_log.stats()
