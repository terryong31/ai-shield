"""Translate demo request options into engine inputs.

This is where credentials stop: the engine only ever sees a ``Clearance`` level.
"""

import hmac
import logging
from dataclasses import replace

from pydantic import SecretStr

from shield_api.schemas import Mode
from shield_api.services.sessions import AttemptLimiter, SessionStore
from shield_engine import Clearance, ShieldConfig

logger = logging.getLogger(__name__)


def resolve_clearance(passphrase: str | None, secret: SecretStr | None) -> Clearance:
    if not passphrase:
        return Clearance.NONE
    if secret is None:
        return Clearance.DENIED
    matches = hmac.compare_digest(
        passphrase.encode("utf-8"), secret.get_secret_value().encode("utf-8")
    )
    return Clearance.GRANTED if matches else Clearance.DENIED


async def clearance_for(
    token: str | None, client: str, sessions: SessionStore, attempts: AttemptLimiter
) -> Clearance:
    """A live session grants clearance; a recent failed guess keeps the stricter ``DENIED``."""
    if token:
        try:
            if await sessions.lookup(token) is not None:
                return Clearance.GRANTED
        except Exception:
            # Fail closed: a broken store must never grant, nor break the request.
            logger.exception("session lookup failed; treating the caller as uncleared")
    return Clearance.DENIED if attempts.failed_recently(client) else Clearance.NONE


def config_for_mode(mode: Mode, base: ShieldConfig) -> ShieldConfig:
    match mode:
        case "shield":
            return base
        case "guardrail":
            return replace(base, always_adjudicate=True)
        case "chaos":
            return replace(base, skip_classifier=True)
