"""Daily provider spend for each player, in Redis with a local fallback (spec 0050)."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from shield_api.schemas import PlayerTier

logger = logging.getLogger(__name__)

# Provider money one player may use in a UTC day. Counts alone do not protect the money:
# one wave costs from $0.0003 to $0.37 (spec 0050, Spend protection).
DAILY_PROVIDER_BUDGET_USD: dict[PlayerTier, float] = {
    "anonymous": 0.02,
    "free": 0.02,
    "paid": 0.10,
}
_MICRO = 1_000_000
_KEY_TTL_SECONDS = 2 * 24 * 3600


class SpendBudgetExceededError(Exception):
    """The player used today's provider budget."""


def _day(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%d")


def _key(owner: str, day: str) -> str:
    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()
    return f"spend:{day}:{digest}"


def next_reset(now: datetime) -> datetime:
    """The start of the next UTC day, when every budget resets."""
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start + timedelta(days=1)


class SpendLedger:
    """Micro-dollar counters per owner per UTC day."""

    def __init__(
        self,
        *,
        redis_client: Any = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._redis = redis_client
        self._clock = clock
        self._local: dict[str, int] = {}

    async def spent(self, owner: str) -> float:
        key = _key(owner, _day(self._clock()))
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                return int(raw or 0) / _MICRO
            except Exception as exc:
                logger.warning(
                    "Redis spend read failed; using local counter (%s)", type(exc).__name__
                )
        return self._local.get(key, 0) / _MICRO

    async def add(self, owner: str, usd: float) -> None:
        micro = max(0, round(usd * _MICRO))
        if micro == 0:
            return
        key = _key(owner, _day(self._clock()))
        if self._redis is not None:
            try:
                await self._redis.incrby(key, micro)
                await self._redis.expire(key, _KEY_TTL_SECONDS)
                return
            except Exception as exc:
                logger.warning(
                    "Redis spend write failed; using local counter (%s)", type(exc).__name__
                )
        self._local[key] = self._local.get(key, 0) + micro

    async def ensure_within(self, owner: str, tier: PlayerTier) -> None:
        budget = DAILY_PROVIDER_BUDGET_USD[tier]
        if await self.spent(owner) >= budget:
            reset = next_reset(self._clock())
            raise SpendBudgetExceededError(
                f"You used today's model budget of ${budget:.2f}. It resets at {reset:%H:%M} UTC."
            )
