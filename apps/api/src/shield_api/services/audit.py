"""Structured audit records for sensitive actions (spec 0054).

A record names the event, a hash of the actor, the client address and the outcome.
It never holds a password, a token or a plain email address.
"""

import json
import logging

from shield_api.services.models import account_hash

logger = logging.getLogger("shield_api.audit")


def actor_hash(email: str | None) -> str | None:
    """A short, stable hash of an email address, for joining records without the address."""
    return account_hash(email)[:16] if email else None


def audit(
    event: str,
    *,
    outcome: str,
    actor: str | None = None,
    client: str | None = None,
    warning: bool = False,
) -> None:
    record = {"event": event, "outcome": outcome, "actor": actor_hash(actor), "client": client}
    logger.log(logging.WARNING if warning else logging.INFO, json.dumps(record))
