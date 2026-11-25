"""Account settings: change password and email, reset progress, delete account (spec 0025).

Every action needs a signed-in (not anonymous) player and their current
password. With Supabase configured, Supabase Auth checks and changes the
password and email (spec 0027); otherwise the local PBKDF2 hash is used.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from shield_api.container import Container
from shield_api.dependencies import PLAYER_SESSION_COOKIE, ContainerDep, enforce_rate_limit
from shield_api.schemas import (
    AccountDeleteRequest,
    AccountEmailRequest,
    AccountPasswordRequest,
    AccountResetRequest,
    AccountResetResponse,
    PlayerConfirmationResponse,
    PlayerSessionStatus,
)
from shield_api.services.auth_flows import (
    BROWSER_COOKIE_NAME,
    SIGNUP_FLOW_TTL_SECONDS,
    AuthFlowRecord,
    hash_browser_cookie,
)
from shield_api.services.identity import (
    EmailNotConfirmedError,
    IdentityConflictError,
    IdentityUnavailableError,
    InvalidIdentityError,
)
from shield_api.services.rate_limit import (
    ACCOUNT_EMAIL_LIMIT,
    ACCOUNT_EMAIL_WINDOW,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/account", tags=["Account"])

SIGN_IN_REQUIRED = "Sign in to manage your account."
WRONG_PASSWORD = "The current password is not correct."  # noqa: S105 (a message)
TOO_MANY = "Too many attempts. Try again later."
EMAIL_TAKEN = "An account with this email already exists."
UNAVAILABLE = "Your account could not be updated. Try again later."

_COMMON: dict[int | str, dict[str, Any]] = {
    401: {"description": "The current password is not correct."},
    403: {"description": "Sign in to manage your account."},
    429: {"description": "Too many wrong passwords for this account."},
    503: {"description": "The change could not be completed."},
}


async def _player(request: Request, container: Container) -> tuple[str, str]:
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    player = await container.players.lookup(token)
    if not token or not player.authenticated or player.is_anonymous or not player.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SIGN_IN_REQUIRED)
    return token, player.email


async def _reauthenticate(container: Container, email: str, password: str) -> str:
    """Check the current password via Supabase Auth and return the user id."""
    key = f"account:{email}"
    window_seconds = container.settings.CLEARANCE_WINDOW_MINUTES * 60
    max_attempts = container.settings.CLEARANCE_MAX_ATTEMPTS
    if container.rate_limiter._redis is not None:
        try:
            await container.rate_limiter.check_only(
                "account_reauth", email, limit=max_attempts, window_seconds=window_seconds
            )
        except RateLimitExceededError as err:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                TOO_MANY,
                headers={"Retry-After": str(err.retry_after)},
            ) from None
    retry_after = container.attempts.retry_after(key)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY, headers={"Retry-After": str(retry_after)}
        )
    user_id: str | None = None
    try:
        user_id = (await container.identity.verify(email, password)).user_id
    except (InvalidIdentityError, EmailNotConfirmedError):
        user_id = None
    except IdentityUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    if user_id is None:
        container.attempts.record_failure(key)
        if container.rate_limiter._redis is not None:
            await container.rate_limiter.record_failure(
                "account_reauth", email, window_seconds=window_seconds
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG_PASSWORD)
    container.attempts.reset(key)
    if container.rate_limiter._redis is not None:
        await container.rate_limiter.reset("account_reauth", email, window_seconds=window_seconds)
    return user_id


async def _store[T](step: Awaitable[T]) -> T:
    """Run a store write; any failure is a generic 503 (details stay in the log)."""
    try:
        return await step
    except HTTPException:
        raise
    except Exception:
        logger.exception("account update failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None


@router.post("/password", responses=_COMMON)
async def change_password(
    body: AccountPasswordRequest, request: Request, container: ContainerDep
) -> PlayerSessionStatus:
    """Change the password and sign out every other session."""
    token, email = await _player(request, container)
    user_id = await _reauthenticate(container, email, body.current_password)
    try:
        await container.identity.update_password(user_id, body.new_password)
    except (IdentityUnavailableError, IdentityConflictError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    await _store(container.players.revoke_sessions(email, keep=token))
    await container.models.purge_account(email, keep_token=token)
    return await container.players.lookup(token)


@router.post(
    "/email",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_COMMON, 409: {"description": "An account with this email already exists."}},
)
async def change_email(
    body: AccountEmailRequest, request: Request, container: ContainerDep
) -> PlayerConfirmationResponse:
    """Start a confirmed email change through Supabase Auth (spec 0042)."""
    _, email = await _player(request, container)
    new_email = body.new_email.strip().lower()
    if new_email == email:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "The new email is the same as the current one."
        )
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "account_email",
            email,
            limit=ACCOUNT_EMAIL_LIMIT,
            window_seconds=ACCOUNT_EMAIL_WINDOW,
        )
    await _reauthenticate(container, email, body.current_password)
    if await _store(container.players.email_taken(new_email)):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)

    browser_hash = hash_browser_cookie(request.cookies.get(BROWSER_COOKIE_NAME))
    flow_id = await container.auth_flows.create(
        AuthFlowRecord(purpose="email_change", browser_hash=browser_hash),
        ttl_seconds=SIGNUP_FLOW_TTL_SECONDS,
    )
    web_base = container.settings.WEB_BASE_URL.strip().rstrip("/")
    redirect_to = f"{web_base}/auth/confirmed?flow={flow_id}&intent=email_change"
    try:
        await container.identity.request_email_change(
            email, body.current_password, new_email, redirect_to=redirect_to
        )
    except IdentityConflictError:
        await container.auth_flows.delete(flow_id)
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None
    except IdentityUnavailableError:
        await container.auth_flows.delete(flow_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    return PlayerConfirmationResponse()


@router.post("/reset-progress", responses=_COMMON)
async def reset_progress(
    body: AccountResetRequest, request: Request, container: ContainerDep
) -> AccountResetResponse:
    """Delete this account's leaderboard scores and saved boards. The account stays."""
    _, email = await _player(request, container)
    await _reauthenticate(container, email, body.current_password)
    scores_removed = await _store(container.scores.delete_scores_for(email))
    boards_removed = await _store(container.players.delete_boards(email))
    if scores_removed > 0:
        await container.leaderboard.on_owner_deleted(email)
    return AccountResetResponse(scores_removed=scores_removed, boards_removed=boards_removed)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, responses=_COMMON)
async def delete_account(
    body: AccountDeleteRequest, request: Request, container: ContainerDep
) -> Response:
    """Delete the account and everything it owns, except today's run counts."""
    _, email = await _player(request, container)
    user_id = await _reauthenticate(container, email, body.current_password)
    # Gateway data first, the Supabase user last, so a failure can be retried.
    await _store(container.players.delete_boards(email))
    scores_removed = await _store(container.scores.delete_scores_for(email))
    if scores_removed > 0:
        await container.leaderboard.on_owner_deleted(email)
    await container.models.purge_account(email)
    await _store(container.players.delete_account(email))
    try:
        await container.identity.delete_user(user_id)
    except (IdentityUnavailableError, IdentityConflictError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None

    settings = container.settings
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        PLAYER_SESSION_COOKIE,
        path=settings.API_PREFIX,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return response
