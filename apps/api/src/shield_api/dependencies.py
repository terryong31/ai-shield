from typing import Annotated

from fastapi import Depends, Request

from shield_api.container import Container
from shield_api.services.access import clearance_for
from shield_engine import Clearance

SESSION_COOKIE = "shield_session"


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def client_address(request: Request) -> str:
    # Forwarded headers are client-controlled; trust only the socket peer.
    return request.client.host if request.client else "unknown"


async def get_clearance(request: Request, container: ContainerDep) -> Clearance:
    return await clearance_for(
        request.cookies.get(SESSION_COOKIE),
        client_address(request),
        container.sessions,
        container.attempts,
    )


ClearanceDep = Annotated[Clearance, Depends(get_clearance)]
