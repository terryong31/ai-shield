"""Who may hold admin clearance (spec 0012, "Admin accounts").

An admin is a Supabase Auth user whose ``app_metadata.role`` is ``"admin"``.
``app_metadata`` can only be written with the service key, so users cannot
grant it to themselves; ``user_metadata`` is user-writable and never trusted.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

ADMIN_ROLE = "admin"


@dataclass(frozen=True)
class AdminIdentity:
    user_id: str
    email: str


class AdminAuthenticator(Protocol):
    async def authenticate(self, email: str, password: str) -> AdminIdentity | None:
        """The admin these credentials belong to, or ``None`` for any failure."""
        ...


def is_admin_user(user: Any) -> bool:
    metadata = getattr(user, "app_metadata", None) or {}
    return isinstance(metadata, dict) and metadata.get("role") == ADMIN_ROLE


class SupabaseAdminAuthenticator:
    """Checks the password with Supabase Auth, then the role.

    ``client_factory`` returns a fresh client per check, so signing in never
    changes the auth state of a client shared with the data stores.
    """

    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._client_factory = client_factory

    async def authenticate(self, email: str, password: str) -> AdminIdentity | None:
        return await asyncio.to_thread(self._authenticate, email, password)

    def _authenticate(self, email: str, password: str) -> AdminIdentity | None:
        client = self._client_factory()
        try:
            response = client.auth.sign_in_with_password({"email": email, "password": password})
        except Exception:
            # Wrong password, unknown user or an outage: all look the same to the caller.
            logger.debug("admin sign-in refused by Supabase Auth")
            return None
        try:
            user = getattr(response, "user", None)
            if user is None or not is_admin_user(user):
                logger.warning("admin sign-in refused: account is not an admin")
                return None
            return AdminIdentity(user_id=str(user.id), email=str(user.email or email))
        finally:
            # The password-grade Supabase session is not needed past this check.
            try:
                client.auth.sign_out()
            except Exception:
                logger.debug("best-effort Supabase sign-out failed")
