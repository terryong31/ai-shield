import ipaddress
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from shield_api.container import Container
from shield_api.security import proxy_secret_matches
from shield_api.services.clearance import Clearance, clearance_for
from shield_api.services.rate_limit import RateLimiter, RateLimitExceededError
from shield_api.settings import Settings

SESSION_COOKIE = "shield_session"
PLAYER_SESSION_COOKIE = "shield_player_session"


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def client_address(request: Request, settings: Settings | None = None) -> str:
    """Resolve client IP from a trusted proxy header when configured and authorized."""
    peer = request.client.host if request.client else "unknown"
    if settings is None:
        app = getattr(request, "app", None)
        state = getattr(app, "state", None)
        container = getattr(state, "container", None)
        settings = getattr(container, "settings", None)
    if settings is None or not settings.TRUSTED_CLIENT_IP_HEADER:
        return peer

    # Trust the header only from the proxy that proves the shared secret (spec 0054).
    if not proxy_secret_matches(settings, request.headers.get("x-shield-proxy-secret", "")):
        return peer

    # The rightmost entry is the hop that the trusted proxy appended itself.
    raw = request.headers.get(settings.TRUSTED_CLIENT_IP_HEADER, "")
    last = raw.rsplit(",", 1)[-1].strip()
    if not last:
        return peer
    try:
        return str(ipaddress.ip_address(last))
    except ValueError:
        return peer


async def enforce_rate_limit(
    limiter: RateLimiter,
    bucket: str,
    raw_key: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    try:
        await limiter.check_and_increment(
            bucket, raw_key, limit=limit, window_seconds=window_seconds
        )
    except RateLimitExceededError as err:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            err.detail,
            headers={"Retry-After": str(err.retry_after)},
        ) from None


async def get_clearance(request: Request, container: ContainerDep) -> Clearance:
    return await clearance_for(
        request.cookies.get(SESSION_COOKIE),
        client_address(request),
        container.sessions,
        container.attempts,
    )


ClearanceDep = Annotated[Clearance, Depends(get_clearance)]
