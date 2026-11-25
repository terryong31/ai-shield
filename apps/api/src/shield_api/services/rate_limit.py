"""Fixed-window gateway rate limiter with Redis backend and local fallback (spec 0043)."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Production limits (spec 0043). Never applied in APP_ENV="development".
AUTH_IP_LIMIT = 30
AUTH_IP_WINDOW = 300
LOGIN_FAIL_EMAIL_LIMIT = 10
LOGIN_FAIL_EMAIL_WINDOW = 900
ANON_IP_LIMIT = 30
ANON_IP_WINDOW = 3600
EMAIL_SEND_LIMIT = 1
EMAIL_SEND_WINDOW = 60
GAME_RUN_IP_LIMIT = 30
GAME_RUN_IP_WINDOW = 60
GAME_RUN_ACTOR_LIMIT = 10
GAME_RUN_ACTOR_WINDOW = 60
GAME_TRAIN_EMAIL_LIMIT = 10
GAME_TRAIN_EMAIL_WINDOW = 60


class RateLimitExceededError(Exception):
    """Raised when a fixed-window rate limit bucket is exceeded."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, int(retry_after))
        self.detail = f"Too many requests. Try again in {self.retry_after} seconds."
        super().__init__(self.detail)


def hashed_bucket_key(bucket: str, raw_key: str, window: int) -> str:
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"rl:{bucket}:{digest}:{window}"


class RateLimiter:
    """Fixed-window counter backed by Redis when configured, with local fallback."""

    def __init__(
        self,
        *,
        redis_client: Any = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis_client
        self._clock = clock
        self._counts: dict[str, int] = {}
        self._expiries: dict[str, float] = {}

    def _window(self, window_seconds: int) -> tuple[int, int, float]:
        now = self._clock()
        win = int(now // window_seconds)
        end = (win + 1) * window_seconds
        retry_after = max(1, math.ceil(end - now))
        return win, retry_after, float(end)

    def _prune(self, now: float) -> None:
        expired = [k for k, exp in self._expiries.items() if exp <= now]
        for key in expired:
            self._expiries.pop(key, None)
            self._counts.pop(key, None)

    def _local_incr(self, key: str, expires_at: float) -> int:
        self._prune(self._clock())
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        self._expiries.setdefault(key, expires_at)
        return count

    def _local_get(self, key: str) -> int:
        self._prune(self._clock())
        return self._counts.get(key, 0)

    async def check_and_increment(
        self, bucket: str, raw_key: str, *, limit: int, window_seconds: int
    ) -> None:
        win, retry_after, expires_at = self._window(window_seconds)
        key = hashed_bucket_key(bucket, raw_key, win)
        count: int
        if self._redis is not None:
            try:
                count = int(await self._redis.incr(key))
                if count == 1:
                    await self._redis.expire(key, window_seconds)
            except Exception as exc:
                logger.warning(
                    "Redis rate limiter failed; falling back to local counter (%s)",
                    type(exc).__name__,
                )
                count = self._local_incr(key, expires_at)
        else:
            count = self._local_incr(key, expires_at)

        if count > limit:
            raise RateLimitExceededError(retry_after)

    async def check_only(
        self, bucket: str, raw_key: str, *, limit: int, window_seconds: int
    ) -> None:
        win, retry_after, _ = self._window(window_seconds)
        key = hashed_bucket_key(bucket, raw_key, win)
        count = self._local_get(key)
        if self._redis is not None and hasattr(self._redis, "get"):
            try:
                raw = await self._redis.get(key)
                if raw is not None:
                    count = max(count, int(raw))
            except Exception as exc:
                logger.warning(
                    "Redis rate limiter read failed; using local counter (%s)",
                    type(exc).__name__,
                )
        if count >= limit:
            raise RateLimitExceededError(retry_after)

    async def record_failure(self, bucket: str, raw_key: str, *, window_seconds: int) -> None:
        win, _, expires_at = self._window(window_seconds)
        key = hashed_bucket_key(bucket, raw_key, win)
        # Keep local mirror updated so check_only works even against minimal incr/expire fakes.
        self._local_incr(key, expires_at)
        if self._redis is not None:
            try:
                count = int(await self._redis.incr(key))
                if count == 1:
                    await self._redis.expire(key, window_seconds)
            except Exception as exc:
                logger.warning(
                    "Redis rate limiter write failed; local counter active (%s)",
                    type(exc).__name__,
                )
