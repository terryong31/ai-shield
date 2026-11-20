"""Client-level player authentication endpoints (spec 0016)."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from shield_api.container import Container
from shield_api.dependencies import PLAYER_SESSION_COOKIE, ContainerDep
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
from shield_api.services.players import (
    InvalidCredentialsError,
    PlayerAlreadyExistsError,
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
        409: {"description": "An account with this email already exists (local mode only)."},
    },
)
async def register_player(
    body: PlayerRegisterRequest, request: Request, response: Response, container: ContainerDep
) -> Response | PlayerSessionStatus:
    """Register a player on the free tier.

    With Supabase, the player must confirm their email before signing in.
    """
    email = body.email.strip().lower()
    if container.identity is not None:
        player = await container.identity.register(email, body.password, body.player_name)
        if player is None:
            return _confirmation_sent()
        return await _open_verified(player, request, response, container)

    settings = container.settings
    if previous := request.cookies.get(PLAYER_SESSION_COOKIE):
        await container.players.revoke(previous)

    ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)
    try:
        token, session_status = await container.players.register(
            email=email,
            password=body.password,
            player_name=body.player_name,
            ttl=ttl,
        )
    except PlayerAlreadyExistsError as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from err

    _set_player_cookie(response, token, settings, ttl)
    return session_status


@router.post(
    "/login",
    responses={
        401: {"description": "Invalid email or password."},
        403: {"description": "The email has not been confirmed yet."},
        503: {"description": "Sign-in is unavailable."},
    },
)
async def login_player(
    body: PlayerLoginRequest, request: Request, response: Response, container: ContainerDep
) -> PlayerSessionStatus:
    """Sign in an existing player account."""
    email = body.email.strip().lower()
    if container.identity is not None:
        try:
            player = await container.identity.verify(email, body.password)
        except InvalidIdentityError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN) from None
        except EmailNotConfirmedError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_CONFIRMED) from None
        except IdentityUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
        return await _open_verified(player, request, response, container)

    settings = container.settings
    if previous := request.cookies.get(PLAYER_SESSION_COOKIE):
        await container.players.revoke(previous)

    ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)
    try:
        token, session_status = await container.players.login(
            email=email,
            password=body.password,
            ttl=ttl,
        )
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN) from None

    _set_player_cookie(response, token, settings, ttl)
    return session_status


@router.post(
    "/resend-confirmation",
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_confirmation(
    body: PlayerResendRequest, container: ContainerDep
) -> PlayerConfirmationResponse:
    """Send the confirmation email again. The answer is the same for every address."""
    if container.identity is not None:
        await container.identity.resend(body.email.strip().lower())
    return PlayerConfirmationResponse()


@router.post("/recover")
async def recover_player_password(
    body: PlayerRecoverRequest, container: ContainerDep
) -> PlayerRecoverResponse:
    """Trigger a password recovery email via Supabase Auth when configured."""
    settings = container.settings
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        try:
            from supabase import create_client

            sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY.get_secret_value())
            sb.auth.reset_password_for_email(body.email.strip())
        except Exception:
            logger.debug("Supabase reset_password_for_email skipped or unavailable")
    return PlayerRecoverResponse()


@router.post(
    "/upgrade",
    responses={403: {"description": "Sign in required to upgrade plan."}},
)
async def upgrade_player_plan(request: Request, container: ContainerDep) -> PlayerSessionStatus:
    """Upgrade the currently signed-in player from the free tier to the paid tier."""
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
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        PLAYER_SESSION_COOKIE,
        path=settings.API_PREFIX,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return response
