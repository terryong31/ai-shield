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
from shield_api.dependencies import PLAYER_SESSION_COOKIE, ContainerDep
from shield_api.schemas import (
    AccountDeleteRequest,
    AccountEmailRequest,
    AccountPasswordRequest,
    AccountResetRequest,
    AccountResetResponse,
    PlayerSessionStatus,
)
from shield_api.services.identity import (
    EmailNotConfirmedError,
    IdentityConflictError,
    IdentityUnavailableError,
    InvalidIdentityError,
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


async def _reauthenticate(container: Container, email: str, password: str) -> str | None:
    """Check the current password; returns the Supabase user id in Supabase mode."""
    key = f"account:{email}"
    retry_after = container.attempts.retry_after(key)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY, headers={"Retry-After": str(retry_after)}
        )
    user_id: str | None = None
    if container.identity is not None:
        try:
            user_id = (await container.identity.verify(email, password)).user_id
            ok = user_id is not None
        except (InvalidIdentityError, EmailNotConfirmedError):
            ok = False
        except IdentityUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    else:
        ok = await container.players.verify_password(email, password)
    if not ok:
        container.attempts.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG_PASSWORD)
    container.attempts.reset(key)
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
    if container.identity is not None and user_id is not None:
        try:
            await container.identity.update_password(user_id, body.new_password)
        except (IdentityUnavailableError, IdentityConflictError):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    else:
        await _store(container.players.set_password(email, body.new_password))
    await _store(container.players.revoke_sessions(email, keep=token))
    return await container.players.lookup(token)


@router.post(
    "/email",
    responses={**_COMMON, 409: {"description": "An account with this email already exists."}},
)
async def change_email(
    body: AccountEmailRequest, request: Request, container: ContainerDep
) -> PlayerSessionStatus:
    """Move the account, its scores, saved boards, usage and sessions to a new email."""
    token, email = await _player(request, container)
    new_email = body.new_email.strip().lower()
    if new_email == email:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "The new email is the same as the current one."
        )
    user_id = await _reauthenticate(container, email, body.current_password)
    if await _store(container.players.email_taken(new_email)):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)

    identity = container.identity if user_id is not None else None
    if identity is not None and user_id is not None:
        try:
            await identity.update_email(user_id, new_email)
        except IdentityConflictError:
            raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None
        except IdentityUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    try:
        # Scores, then boards, usage, sessions and the account row last (spec 0025).
        await container.scores.rename_scores_email(email, new_email)
        await container.players.move_email(email, new_email)
    except Exception:
        logger.exception("email change failed")
        if identity is not None and user_id is not None:
            try:
                await identity.update_email(user_id, email)
            except Exception:
                logger.exception("could not restore the Supabase email after a failed move")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    return await container.players.lookup(token)


@router.post("/reset-progress", responses=_COMMON)
async def reset_progress(
    body: AccountResetRequest, request: Request, container: ContainerDep
) -> AccountResetResponse:
    """Delete this account's leaderboard scores and saved boards. The account stays."""
    _, email = await _player(request, container)
    await _reauthenticate(container, email, body.current_password)
    scores_removed = await _store(container.scores.delete_scores_for(email))
    boards_removed = await _store(container.players.delete_boards(email))
    if scores_removed > 0 and hasattr(container, "leaderboard_notifier"):
        from shield_api.services.scores import RedisCachedScoreStore

        if not isinstance(container.scores, RedisCachedScoreStore):
            await container.leaderboard_notifier.publish(level_id=None, reason="deleted")
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
    if scores_removed > 0 and hasattr(container, "leaderboard_notifier"):
        from shield_api.services.scores import RedisCachedScoreStore

        if not isinstance(container.scores, RedisCachedScoreStore):
            await container.leaderboard_notifier.publish(level_id=None, reason="deleted")
    await _store(container.players.delete_account(email))
    if container.identity is not None and user_id is not None:
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
