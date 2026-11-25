"""Client-level player authentication endpoints (spec 0016)."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from shield_api.container import Container
from shield_api.dependencies import (
    PLAYER_SESSION_COOKIE,
    ContainerDep,
    client_address,
    enforce_rate_limit,
)
from shield_api.schemas import (
    PlayerConfirmationResponse,
    PlayerLoginRequest,
    PlayerRecoverRequest,
    PlayerRecoverResponse,
    PlayerRegisterRequest,
    PlayerResendRequest,
    PlayerSessionStatus,
)
from shield_api.services.identity import (
    EmailNotConfirmedError,
    IdentityUnavailableError,
    InvalidIdentityError,
    VerifiedPlayer,
)
from shield_api.services.rate_limit import (
    ANON_IP_LIMIT,
    ANON_IP_WINDOW,
    AUTH_IP_LIMIT,
    AUTH_IP_WINDOW,
    EMAIL_SEND_LIMIT,
    EMAIL_SEND_WINDOW,
    LOGIN_FAIL_EMAIL_LIMIT,
    LOGIN_FAIL_EMAIL_WINDOW,
    RateLimitExceededError,
)
from shield_api.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

INVALID_LOGIN = "Invalid email or password."
NOT_CONFIRMED = "Confirm your email before signing in."
UNAVAILABLE = "Sign-in is unavailable. Try again later."


def _set_player_cookie(response: Response, token: str, settings: Settings, ttl: timedelta) -> None:
    response.set_cookie(
        PLAYER_SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        path=settings.API_PREFIX,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


@router.get("/session")
async def get_player_session(request: Request, container: ContainerDep) -> PlayerSessionStatus:
    """Return current player authentication status, tier, and daily run usage."""
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    return await container.players.lookup(token)


@router.post("/anonymous")
async def sign_in_anonymous_player(
    request: Request, response: Response, container: ContainerDep
) -> PlayerSessionStatus:
    """Create a free anonymous player session."""
    settings = container.settings
    if settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "anon_ip",
            client_address(request),
            limit=ANON_IP_LIMIT,
            window_seconds=ANON_IP_WINDOW,
        )
    if previous := request.cookies.get(PLAYER_SESSION_COOKIE):
        await container.players.revoke(previous)

    ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)
    token, session_status = await container.players.create_anonymous(ttl)
    _set_player_cookie(response, token, settings, ttl)
    return session_status


async def _open_verified(
    player: VerifiedPlayer, request: Request, response: Response, container: Container
) -> PlayerSessionStatus:
    settings = container.settings
    if player.profile_email is not None and player.profile_email != player.email:
        try:
            await container.scores.rename_scores_email(player.profile_email, player.email)
            await container.leaderboard.on_owner_renamed(player.profile_email, player.email)
            await container.players.move_email(player.profile_email, player.email)
        except Exception:
            logger.exception("deferred email change move failed on sign-in")
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    if player.user_id is not None and player.profile_email != player.email:
        try:
            await container.identity.set_profile_email(
                player.user_id, player.email, player.app_metadata
            )
        except IdentityUnavailableError:
            logger.exception("failed to record profile_email in app_metadata")
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None

    if previous := request.cookies.get(PLAYER_SESSION_COOKIE):
        await container.players.revoke(previous)
    ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)
    token, session_status = await container.players.sign_in_verified(
        email=player.email, player_name=player.player_name, ttl=ttl
    )
    _set_player_cookie(response, token, settings, ttl)
    return session_status


def _confirmation_sent() -> JSONResponse:
    return JSONResponse(
        PlayerConfirmationResponse().model_dump(), status_code=status.HTTP_202_ACCEPTED
    )


@router.post(
    "/register",
    response_model=PlayerSessionStatus,
    responses={
        202: {
            "model": PlayerConfirmationResponse,
            "description": "Check your email: sent for every address when confirmation is on.",
        },
    },
)
async def register_player(
    body: PlayerRegisterRequest, request: Request, response: Response, container: ContainerDep
) -> Response | PlayerSessionStatus:
    """Register a player on the free tier via Supabase Auth."""
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "auth_ip",
            client_address(request),
            limit=AUTH_IP_LIMIT,
            window_seconds=AUTH_IP_WINDOW,
        )
    email = body.email.strip().lower()
    player = await container.identity.register(email, body.password, body.player_name)
    if player is None:
        return _confirmation_sent()
    return await _open_verified(player, request, response, container)


@router.post(
    "/login",
    responses={
        401: {"description": "Invalid email or password."},
        403: {"description": "The email has not been confirmed yet."},
        429: {"description": "Too many requests."},
        503: {"description": "Sign-in is unavailable."},
    },
)
async def login_player(
    body: PlayerLoginRequest, request: Request, response: Response, container: ContainerDep
) -> PlayerSessionStatus:
    """Sign in an existing player account."""
    email = body.email.strip().lower()
    is_prod = container.settings.APP_ENV == "production"
    if is_prod:
        await enforce_rate_limit(
            container.rate_limiter,
            "auth_ip",
            client_address(request),
            limit=AUTH_IP_LIMIT,
            window_seconds=AUTH_IP_WINDOW,
        )
        try:
            await container.rate_limiter.check_only(
                "login_fail",
                email,
                limit=LOGIN_FAIL_EMAIL_LIMIT,
                window_seconds=LOGIN_FAIL_EMAIL_WINDOW,
            )
        except RateLimitExceededError as err:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                err.detail,
                headers={"Retry-After": str(err.retry_after)},
            ) from None
    try:
        player = await container.identity.verify(email, body.password)
    except InvalidIdentityError:
        if is_prod:
            await container.rate_limiter.record_failure(
                "login_fail", email, window_seconds=LOGIN_FAIL_EMAIL_WINDOW
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN) from None
    except EmailNotConfirmedError:
        if is_prod:
            await container.rate_limiter.record_failure(
                "login_fail", email, window_seconds=LOGIN_FAIL_EMAIL_WINDOW
            )
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_CONFIRMED) from None
    except IdentityUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    return await _open_verified(player, request, response, container)


@router.post(
    "/resend-confirmation",
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_confirmation(
    body: PlayerResendRequest, request: Request, container: ContainerDep
) -> PlayerConfirmationResponse:
    """Send the confirmation email again. The answer is the same for every address."""
    email = body.email.strip().lower()
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "auth_ip",
            client_address(request),
            limit=AUTH_IP_LIMIT,
            window_seconds=AUTH_IP_WINDOW,
        )
        await enforce_rate_limit(
            container.rate_limiter,
            "resend_email",
            email,
            limit=EMAIL_SEND_LIMIT,
            window_seconds=EMAIL_SEND_WINDOW,
        )
    await container.identity.resend(email)
    return PlayerConfirmationResponse()


@router.post("/recover")
async def recover_player_password(
    body: PlayerRecoverRequest, request: Request, container: ContainerDep
) -> PlayerRecoverResponse:
    """Trigger a password recovery email via Supabase Auth."""
    email = body.email.strip().lower()
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "auth_ip",
            client_address(request),
            limit=AUTH_IP_LIMIT,
            window_seconds=AUTH_IP_WINDOW,
        )
        await enforce_rate_limit(
            container.rate_limiter,
            "recover_email",
            email,
            limit=EMAIL_SEND_LIMIT,
            window_seconds=EMAIL_SEND_WINDOW,
        )
    await container.identity.recover(email)
    return PlayerRecoverResponse()


@router.post(
    "/upgrade",
    responses={403: {"description": "Paid plans are disabled or sign-in is required."}},
)
async def upgrade_player_plan(request: Request, container: ContainerDep) -> PlayerSessionStatus:
    """Upgrade the currently signed-in player from the free tier to the paid tier."""
    if not container.settings.ALLOW_SELF_UPGRADE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Paid plans are not available yet.")
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    try:
        return await container.players.upgrade(token)
    except PermissionError as err:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(err)) from err


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_player(request: Request, container: ContainerDep) -> Response:
    """End the current player session and clear the session cookie."""
    settings = container.settings
    if token := request.cookies.get(PLAYER_SESSION_COOKIE):
        await container.players.revoke(token)
        await container.models.purge_session(token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        PLAYER_SESSION_COOKIE,
        path=settings.API_PREFIX,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return response
