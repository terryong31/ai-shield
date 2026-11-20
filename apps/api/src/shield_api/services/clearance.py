"""Admin clearance for the `/_console` and admin-only game routes (spec 0012).

Credentials are checked once, at ``POST /clearance``; callers only ever see a
``Clearance`` level.
"""

import logging
from enum import StrEnum

from shield_api.services.sessions import AttemptLimiter, SessionStore

logger = logging.getLogger(__name__)


class Clearance(StrEnum):
    """What the gateway established about the caller's admin privileges.

    ``DENIED`` means clearance was claimed but did not verify.
    """

    NONE = "NONE"
    DENIED = "DENIED"
    GRANTED = "GRANTED"


async def clearance_for(
    token: str | None, client: str, sessions: SessionStore, attempts: AttemptLimiter
) -> Clearance:
    """A live session grants clearance; a recent failed sign-in keeps the stricter ``DENIED``."""
    if token:
        try:
            if await sessions.lookup(token) is not None:
                return Clearance.GRANTED
        except Exception:
            # Fail closed: a broken store must never grant, nor break the request.
            logger.exception("session lookup failed; treating the caller as uncleared")
    return Clearance.DENIED if attempts.failed_recently(client) else Clearance.NONE
