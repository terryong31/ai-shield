import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status

from shield_api.dependencies import SESSION_COOKIE, ContainerDep, client_address
from shield_api.schemas import ClearanceRequest, ClearanceStatus
from shield_api.services.access import resolve_clearance
from shield_engine import Clearance

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Clearance"])

# Identical for a wrong passphrase and an unconfigured one (API-CLEAR-002).
NOT_GRANTED = "Access was not granted."
TOO_MANY = "Too many attempts. Try again later."


@router.post(
    "/clearance",
    responses={
        401: {"description": "The passphrase was not accepted."},
        429: {"description": "Too many failed attempts from this address."},
    },
)
async def grant_clearance(
    body: ClearanceRequest, request: Request, response: Response, container: ContainerDep
) -> ClearanceStatus:
    """Exchange the passphrase for a session cookie. The passphrase is never stored."""
    settings = container.settings
    client = client_address(request)

    retry_after = container.attempts.retry_after(client)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY, headers={"Retry-After": str(retry_after)}
        )

    granted = resolve_clearance(body.passphrase, settings.SECURE_PASSPHRASE) is Clearance.GRANTED
    if not granted and body.email and settings.SUPABASE_URL and settings.SUPABASE_KEY:
        try:
            from supabase import create_client

            sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY.get_secret_value())
            auth_res = sb.auth.sign_in_with_password(
                {"email": body.email, "password": body.passphrase}
            )
            granted = auth_res.user is not None
        except Exception:
            granted = False

    if not granted:
        container.attempts.record_failure(client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_GRANTED)

    container.attempts.reset(client)
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
