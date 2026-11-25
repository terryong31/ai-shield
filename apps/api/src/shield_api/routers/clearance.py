import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status

from shield_api.dependencies import SESSION_COOKIE, ContainerDep, client_address
from shield_api.schemas import ClearanceRequest, ClearanceStatus
from shield_api.services.rate_limit import RateLimitExceededError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Clearance"])

# Identical for every refusal, so it reveals nothing about the account (API-CLEAR-015).
NOT_GRANTED = "Access was not granted."
TOO_MANY = "Too many attempts. Try again later."


@router.post(
    "/clearance",
    responses={
        401: {"description": "The credentials do not belong to an admin."},
        429: {"description": "Too many failed attempts from this address."},
    },
)
async def grant_clearance(
    body: ClearanceRequest, request: Request, response: Response, container: ContainerDep
) -> ClearanceStatus:
    """Exchange an admin's email and password for a session cookie. Neither is stored.

    An admin is a Supabase Auth user whose ``app_metadata.role`` is ``"admin"``.
    """
    settings = container.settings
    client = client_address(request)
    window_seconds = settings.CLEARANCE_WINDOW_MINUTES * 60

    if container.rate_limiter._redis is not None:
        try:
            await container.rate_limiter.check_only(
                "clearance_fail",
                client,
                limit=settings.CLEARANCE_MAX_ATTEMPTS,
                window_seconds=window_seconds,
            )
        except RateLimitExceededError as err:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                TOO_MANY,
                headers={"Retry-After": str(err.retry_after)},
            ) from None

    retry_after = container.attempts.retry_after(client)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY, headers={"Retry-After": str(retry_after)}
        )

    admin = await container.admins.authenticate(body.email.strip().lower(), body.password)
    if admin is None:
        container.attempts.record_failure(client)
        if container.rate_limiter._redis is not None:
            await container.rate_limiter.record_failure(
                "clearance_fail", client, window_seconds=window_seconds
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_GRANTED)

    container.attempts.reset(client)
    if container.rate_limiter._redis is not None:
        await container.rate_limiter.reset("clearance_fail", client, window_seconds=window_seconds)
    if previous := request.cookies.get(SESSION_COOKIE):
        await container.sessions.revoke(previous)

    ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)
    token, expires_at = await container.sessions.create(ttl)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        path=settings.API_PREFIX,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return ClearanceStatus(granted=True, expires_at=expires_at)


@router.get("/clearance")
async def clearance_status(request: Request, container: ContainerDep) -> ClearanceStatus:
    """Whether this browser holds a live session."""
    token = request.cookies.get(SESSION_COOKIE)
    expires_at = None
    if token:
        try:
            expires_at = await container.sessions.lookup(token)
        except Exception:
            logger.exception("session lookup failed")
    return ClearanceStatus(granted=expires_at is not None, expires_at=expires_at)


@router.delete("/clearance", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_clearance(request: Request, container: ContainerDep) -> Response:
    """End the session. Safe to call without one."""
    settings = container.settings
    if token := request.cookies.get(SESSION_COOKIE):
        await container.sessions.revoke(token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        SESSION_COOKIE,
        path=settings.API_PREFIX,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return response
