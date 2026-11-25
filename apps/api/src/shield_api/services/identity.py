"""Who a player is, when Supabase Auth owns their password (spec 0027).

Supabase checks the password and the email confirmation; the gateway keeps its
own session cookie, profile, quotas and saves. Every call uses a throwaway
client, and any Supabase session it opens is signed out at once, so the browser
never holds a Supabase token.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class EmailNotConfirmedError(Exception):
    """The password is right, but the email has not been confirmed yet."""


class IdentityUnavailableError(Exception):
    """Supabase Auth failed for a reason other than the credentials."""


class InvalidIdentityError(Exception):
    """Wrong password or unknown email."""


class IdentityConflictError(Exception):
    """Another Supabase user already has this email."""


@dataclass(frozen=True)
class VerifiedPlayer:
    email: str
    player_name: str | None
    # Supabase Auth user id, for the admin calls in account settings (spec 0025).
    user_id: str | None = None
    # Server-owned gateway email stored in app_metadata (never user_metadata, spec 0042).
    profile_email: str | None = None
    app_metadata: dict[str, Any] = field(default_factory=dict)


class PlayerIdentity(Protocol):
    async def register(
        self, email: str, password: str, player_name: str | None
    ) -> VerifiedPlayer | None:
        """Start sign-up. ``None`` means a confirmation email may have been sent."""
        ...

    async def verify(self, email: str, password: str) -> VerifiedPlayer:
        """Check the credentials, or raise one of this module's errors."""
        ...

    async def resend(self, email: str) -> None:
        """Send the confirmation email again. Never raises."""
        ...

    async def recover(self, email: str) -> None:
        """Send a password recovery email. Never raises."""
        ...

    async def update_password(self, user_id: str, password: str) -> None:
        """Raises ``IdentityUnavailableError``."""
        ...

    async def request_email_change(self, current_email: str, password: str, new_email: str) -> None:
        """Start confirmed email change via the player's own Supabase session.

        Raises ``IdentityConflictError`` or ``IdentityUnavailableError``.
        """
        ...

    async def set_profile_email(
        self, user_id: str, profile_email: str, existing_app_metadata: dict[str, Any] | None = None
    ) -> None:
        """Persist ``app_metadata.profile_email`` via the admin API."""
        ...

    async def delete_user(self, user_id: str) -> None:
        """Raises ``IdentityUnavailableError``."""
        ...


def _player_name(user: Any) -> str | None:
    metadata = getattr(user, "user_metadata", None) or {}
    name = metadata.get("player_name") if isinstance(metadata, dict) else None
    return name.strip() or None if isinstance(name, str) else None


def _app_metadata(user: Any) -> dict[str, Any]:
    raw = getattr(user, "app_metadata", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _profile_email(user: Any) -> str | None:
    raw = _app_metadata(user).get("profile_email")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return None


def _describe(err: Exception) -> str:
    """Error code, HTTP status or exception type; never the message, which can echo input."""
    parts = [str(getattr(err, "code", None) or type(err).__name__)]
    if status := getattr(err, "status", None):
        parts.append(str(status))
    return ", ".join(parts)


def _email_hint(err: Exception) -> str:
    # Supabase sends the confirmation email inside the sign-up request, so a
    # broken mailer shows up here as a timeout or a 5xx and no user is created.
    status = getattr(err, "status", None)
    if "Timeout" in type(err).__name__ or (isinstance(status, int) and status >= 500):
        return ": check the project's SMTP settings and Auth logs"
    return ""


def _sign_out(client: Any) -> None:
    try:
        client.auth.sign_out()
    except Exception:
        logger.debug("best-effort Supabase sign-out failed")


class SupabasePlayerIdentity:
    def __init__(self, client_factory: Callable[[], Any], *, redirect_to: str) -> None:
        self._client_factory = client_factory
        self._redirect_to = redirect_to

    async def register(
        self, email: str, password: str, player_name: str | None
    ) -> VerifiedPlayer | None:
        return await asyncio.to_thread(self._register, email, password, player_name)

    def _register(
        self, email: str, password: str, player_name: str | None
    ) -> VerifiedPlayer | None:
        client = self._client_factory()
        try:
            response = client.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {"player_name": player_name or ""},
                        "email_redirect_to": self._redirect_to,
                    },
                }
            )
        except Exception as err:
            # Same answer for taken emails and outages, so register reveals nothing.
            logger.warning("Supabase sign-up failed (%s)%s", _describe(err), _email_hint(err))
            return None
        if getattr(response, "session", None) is None:
            return None
        # The project has email confirmation off: sign the player in straight away.
        _sign_out(client)
        return VerifiedPlayer(
            email=email,
            player_name=_player_name(response.user) or player_name,
            user_id=str(response.user.id),
            profile_email=_profile_email(response.user),
            app_metadata=_app_metadata(response.user),
        )

    async def verify(self, email: str, password: str) -> VerifiedPlayer:
        return await asyncio.to_thread(self._verify, email, password)

    def _verify(self, email: str, password: str) -> VerifiedPlayer:
        client = self._client_factory()
        try:
            response = client.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as err:
            code = getattr(err, "code", None)
            if code == "invalid_credentials":
                raise InvalidIdentityError from None
            if code == "email_not_confirmed":
                raise EmailNotConfirmedError from None
            logger.warning("Supabase sign-in failed (%s)", code or type(err).__name__)
            raise IdentityUnavailableError from None
        try:
            user = getattr(response, "user", None)
            if user is None:
                raise IdentityUnavailableError
            confirmed_email = str(getattr(user, "email", None) or email).strip().lower()
            return VerifiedPlayer(
                email=confirmed_email,
                player_name=_player_name(user),
                user_id=str(user.id),
                profile_email=_profile_email(user),
                app_metadata=_app_metadata(user),
            )
        finally:
            _sign_out(client)

    def _admin(self, action: str, call: Callable[[Any], Any]) -> None:
        try:
            call(self._client_factory().auth.admin)
        except Exception as err:
            if getattr(err, "code", None) == "email_exists":
                raise IdentityConflictError from None
            logger.warning("Supabase admin %s failed (%s)", action, _describe(err))
            raise IdentityUnavailableError from None

    async def update_password(self, user_id: str, password: str) -> None:
        await asyncio.to_thread(
            self._admin,
            "password update",
            lambda admin: admin.update_user_by_id(user_id, {"password": password}),
        )

    async def request_email_change(self, current_email: str, password: str, new_email: str) -> None:
        await asyncio.to_thread(self._request_email_change, current_email, password, new_email)

    def _request_email_change(self, current_email: str, password: str, new_email: str) -> None:
        client = self._client_factory()
        try:
            client.auth.sign_in_with_password({"email": current_email, "password": password})
            client.auth.update_user({"email": new_email})
        except Exception as err:
            code = getattr(err, "code", None)
            if code == "email_exists":
                raise IdentityConflictError from None
            logger.warning("Supabase email change request failed (%s)", _describe(err))
            raise IdentityUnavailableError from None
        finally:
            _sign_out(client)

    async def set_profile_email(
        self, user_id: str, profile_email: str, existing_app_metadata: dict[str, Any] | None = None
    ) -> None:
        merged = dict(existing_app_metadata or {})
        merged["profile_email"] = profile_email
        await asyncio.to_thread(
            self._admin,
            "profile_email update",
            lambda admin: admin.update_user_by_id(user_id, {"app_metadata": merged}),
        )

    async def delete_user(self, user_id: str) -> None:
        await asyncio.to_thread(
            self._admin, "user delete", lambda admin: admin.delete_user(user_id)
        )

    async def resend(self, email: str) -> None:
        await asyncio.to_thread(self._resend, email)

    def _resend(self, email: str) -> None:
        client = self._client_factory()
        try:
            client.auth.resend(
                {
                    "type": "signup",
                    "email": email,
                    "options": {"email_redirect_to": self._redirect_to},
                }
            )
        except Exception as err:
            logger.warning("Supabase resend failed (%s)%s", _describe(err), _email_hint(err))

    async def recover(self, email: str) -> None:
        await asyncio.to_thread(self._recover, email)

    def _recover(self, email: str) -> None:
        client = self._client_factory()
        try:
            client.auth.reset_password_for_email(email)
        except Exception:
            logger.debug("Supabase reset_password_for_email skipped or unavailable")
