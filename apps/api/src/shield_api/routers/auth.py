"""Client-level player authentication endpoints (spec 0016, 0027, 0047)."""

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
    PlayerConfirmRequest,
    PlayerConfirmResponse,
    PlayerLoginRequest,
    PlayerRecoverRequest,
    PlayerRecoverResponse,
    PlayerRegisterRequest,
    PlayerResendRequest,
    PlayerResetPasswordRequest,
    PlayerResetPasswordResponse,
    PlayerSessionStatus,
)
from shield_api.services.audit import audit
from shield_api.services.auth_flows import (
    BROWSER_COOKIE_NAME,
    RECOVERY_FLOW_TTL_SECONDS,
    SIGNUP_FLOW_TTL_SECONDS,
    AuthFlowRecord,
    browser_cookie_matches,
    hash_browser_cookie,
)
from shield_api.services.identity import (
    EmailNotConfirmedError,
    IdentityUnavailableError,
    InvalidIdentityError,
    InvalidTokenError,
    PasswordRejectedError,
    VerifiedPlayer,
)
from shield_api.services.models import owner_hash
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
REGISTER_UNAVAILABLE = "Registration is unavailable. Try again later."
CONFIRM_INVALID = "This confirmation link is invalid or has expired."
CONFIRM_UNAVAILABLE = "Confirmation is unavailable. Try again later."
RECOVERY_INVALID = "This recovery link is invalid or has expired."
RECOVERY_REJECTED = "This password was not accepted. Request a new link and choose a stronger one."
RECOVERY_UNAVAILABLE = "Password reset is unavailable. Try again later."


def _web_base(settings: Settings) -> str:
    return settings.WEB_BASE_URL.strip().rstrip("/")


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


async def rotate_player_session(
    old_token: str, response: Response, container: Container
) -> PlayerSessionStatus:
    """Give a signed-in player a new session token and revoke the old one (spec 0054).

    The session's trained model moves to the new token, so the player keeps it.
    """
    current = await container.players.lookup(old_token)
    if not current.authenticated or current.is_anonymous or not current.email:
        return current
    ttl = timedelta(minutes=container.settings.SESSION_TTL_MINUTES)
    token, session_status = await container.players.sign_in_verified(
        email=current.email, player_name=current.player_name, ttl=ttl
    )
    if container.model_signing_key is not None:
        await container.models.move_session(
            old_token, token, signing_key=container.model_signing_key
        )
    else:
        await container.models.purge_session(old_token)
    await container.players.revoke(old_token)
    _set_player_cookie(response, token, container.settings, ttl)
    return session_status


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


async def _live_anonymous_owner(previous: str, container: Container) -> str | None:
    """The score key of a live anonymous session, else ``None`` (spec 0052).

    An expired cookie or another player's signed-in cookie gives ``None``, so it
    promotes nothing.
    """
    previous_status = await container.players.lookup(previous)
    if not previous_status.authenticated or not previous_status.is_anonymous:
        return None
    return owner_hash(previous)


async def _promote_anonymous_scores(
    owner: str, signed_in: PlayerSessionStatus, container: Container
) -> None:
    """Move the anonymous scores to the account; a storage error never blocks sign-in."""
    if not signed_in.email:
        return
    try:
        for pending in await container.anonymous_scores.list_for(owner):
            payload = pending.model_copy(update={"player_name": signed_in.player_name})
            change = await container.scores.record_score_change(payload, email=signed_in.email)
            await container.leaderboard.on_score_recorded(signed_in.email, change)
        await container.anonymous_scores.delete_for(owner)
    except Exception:
        logger.exception("anonymous score promotion failed; sign-in continues")


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

    anonymous_owner: str | None = None
    if previous := request.cookies.get(PLAYER_SESSION_COOKIE):
        anonymous_owner = await _live_anonymous_owner(previous, container)
        await container.players.revoke(previous)
    ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)
    token, session_status = await container.players.sign_in_verified(
        email=player.email, player_name=player.player_name, ttl=ttl
    )
    if anonymous_owner is not None:
        await _promote_anonymous_scores(anonymous_owner, session_status, container)
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
        503: {"description": "Registration is unavailable."},
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
    if container.settings.APP_ENV == "production":
        # One sign-up email per address per window, from any IP (spec 0054).
        await enforce_rate_limit(
            container.rate_limiter,
            "register_email",
            email,
            limit=EMAIL_SEND_LIMIT,
            window_seconds=EMAIL_SEND_WINDOW,
        )
    browser_hash = hash_browser_cookie(request.cookies.get(BROWSER_COOKIE_NAME))
    flow_id = await container.auth_flows.create(
        AuthFlowRecord(purpose="signup", browser_hash=browser_hash),
        ttl_seconds=SIGNUP_FLOW_TTL_SECONDS,
    )
    redirect_to = f"{_web_base(container.settings)}/auth/confirmed?flow={flow_id}"
    verifier_out: list[str] = []
    try:
        player = await container.identity.register(
            email,
            body.password,
            body.player_name,
            redirect_to=redirect_to,
            verifier_out=verifier_out,
        )
    except IdentityUnavailableError:
        await container.auth_flows.delete(flow_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, REGISTER_UNAVAILABLE) from None
    if player is None:
        if verifier_out:
            await container.auth_flows.save(
                flow_id,
                AuthFlowRecord(
                    purpose="signup", browser_hash=browser_hash, code_verifier=verifier_out[0]
                ),
                ttl_seconds=SIGNUP_FLOW_TTL_SECONDS,
            )
        return _confirmation_sent()
    await container.auth_flows.delete(flow_id)
    return await _open_verified(player, request, response, container)


@router.post(
    "/confirm",
    responses={
        400: {"description": "Invalid or expired confirmation link."},
        503: {"description": "Confirmation is unavailable."},
    },
)
async def confirm_player_email(
    body: PlayerConfirmRequest, request: Request, response: Response, container: ContainerDep
) -> PlayerConfirmResponse:
    """Confirm an email link; auto-sign-in only when the originating browser cookie matches."""
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "auth_ip",
            client_address(request),
            limit=AUTH_IP_LIMIT,
            window_seconds=AUTH_IP_WINDOW,
        )
    if not body.token_hash and not body.code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, CONFIRM_INVALID)

    flow = await container.auth_flows.get(body.flow_id) if body.flow_id else None
    # A flow of another purpose (a recovery link) is no flow here (spec 0054).
    if flow is not None and flow.purpose != body.type:
        flow = None
    same_browser = flow is not None and browser_cookie_matches(
        flow.browser_hash, request.cookies.get(BROWSER_COOKIE_NAME)
    )

    if same_browser:
        assert flow is not None
        try:
            player = await container.identity.verify_confirmation(
                code=body.code,
                code_verifier=flow.code_verifier,
                token_hash=body.token_hash,
                token_type=body.type,
            )
        except InvalidTokenError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, CONFIRM_INVALID) from None
        except IdentityUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CONFIRM_UNAVAILABLE) from None
        if body.flow_id:
            await container.auth_flows.delete(body.flow_id)
        session_status = await _open_verified(player, request, response, container)
        return PlayerConfirmResponse(status="signed_in", session=session_status)

    if not body.confirm:
        return PlayerConfirmResponse(status="confirmation_required", session=None)

    if body.token_hash:
        try:
            await container.identity.verify_confirmation(
                token_hash=body.token_hash, token_type=body.type
            )
        except InvalidTokenError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, CONFIRM_INVALID) from None
        except IdentityUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CONFIRM_UNAVAILABLE) from None
    elif body.code and flow is not None and flow.code_verifier:
        try:
            await container.identity.verify_confirmation(
                code=body.code, code_verifier=flow.code_verifier, token_type=body.type
            )
        except InvalidTokenError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, CONFIRM_INVALID) from None
        except IdentityUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CONFIRM_UNAVAILABLE) from None
    else:
        # Nothing could be verified, so nothing is confirmed (spec 0054).
        raise HTTPException(status.HTTP_400_BAD_REQUEST, CONFIRM_INVALID)

    if body.flow_id:
        await container.auth_flows.delete(body.flow_id)
    return PlayerConfirmResponse(status="confirmed", session=None)


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
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_CONFIRMED) from None
    except IdentityUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    if is_prod:
        await container.rate_limiter.reset(
            "login_fail", email, window_seconds=LOGIN_FAIL_EMAIL_WINDOW
        )
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
    browser_hash = hash_browser_cookie(request.cookies.get(BROWSER_COOKIE_NAME))
    flow_id = await container.auth_flows.create(
        AuthFlowRecord(purpose="signup", browser_hash=browser_hash),
        ttl_seconds=SIGNUP_FLOW_TTL_SECONDS,
    )
    redirect_to = f"{_web_base(container.settings)}/auth/confirmed?flow={flow_id}"
    await container.identity.resend(email, redirect_to=redirect_to)
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
    browser_hash = hash_browser_cookie(request.cookies.get(BROWSER_COOKIE_NAME))
    flow_id = await container.auth_flows.create(
        AuthFlowRecord(purpose="recovery", browser_hash=browser_hash),
        ttl_seconds=RECOVERY_FLOW_TTL_SECONDS,
    )
    redirect_to = f"{_web_base(container.settings)}/auth/reset-password?flow={flow_id}"
    verifier_out: list[str] = []
    await container.identity.recover(email, redirect_to=redirect_to, verifier_out=verifier_out)
    if verifier_out:
        await container.auth_flows.save(
            flow_id,
            AuthFlowRecord(
                purpose="recovery", browser_hash=browser_hash, code_verifier=verifier_out[0]
            ),
            ttl_seconds=RECOVERY_FLOW_TTL_SECONDS,
        )
    return PlayerRecoverResponse()


@router.post(
    "/reset-password",
    responses={
        400: {"description": "Invalid or expired recovery link."},
        503: {"description": "Password reset is unavailable."},
    },
)
async def reset_player_password(
    body: PlayerResetPasswordRequest, request: Request, container: ContainerDep
) -> PlayerResetPasswordResponse:
    """Complete a password reset from a recovery link and revoke all existing sessions."""
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "auth_ip",
            client_address(request),
            limit=AUTH_IP_LIMIT,
            window_seconds=AUTH_IP_WINDOW,
        )
    if not body.token_hash and not body.code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, RECOVERY_INVALID)

    flow = await container.auth_flows.get(body.flow_id) if body.flow_id else None
    # Only a recovery flow may give its code verifier here (spec 0054).
    if flow is not None and flow.purpose != "recovery":
        flow = None
    try:
        email = await container.identity.complete_password_reset(
            code=body.code,
            code_verifier=flow.code_verifier if flow else None,
            token_hash=body.token_hash,
            new_password=body.new_password,
        )
    except InvalidTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, RECOVERY_INVALID) from None
    except PasswordRejectedError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, RECOVERY_REJECTED) from None
    except IdentityUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, RECOVERY_UNAVAILABLE) from None

    if body.flow_id:
        await container.auth_flows.delete(body.flow_id)
    await container.players.revoke_sessions(email, keep=None)
    await container.models.purge_account(email)
    audit("account.password_reset", outcome="reset", actor=email)
    return PlayerResetPasswordResponse()


@router.post(
    "/upgrade",
    responses={403: {"description": "Paid plans are disabled or sign-in is required."}},
)
async def upgrade_player_plan(
    request: Request, response: Response, container: ContainerDep
) -> PlayerSessionStatus:
    """Upgrade the currently signed-in player from the free tier to the paid tier."""
    if not container.settings.ALLOW_SELF_UPGRADE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Paid plans are not available yet.")
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    try:
        await container.players.upgrade(token)
    except PermissionError as err:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(err)) from err
    assert token is not None
    # A change of privilege gets a new session token (spec 0054).
    return await rotate_player_session(token, response, container)


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
