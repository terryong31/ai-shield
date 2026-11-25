"""Short-lived auth flow records binding email links to the originating browser (spec 0047)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

BROWSER_COOKIE_NAME = "shield_auth_browser"
BROWSER_COOKIE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
SIGNUP_FLOW_TTL_SECONDS = 3600
RECOVERY_FLOW_TTL_SECONDS = 1800

AuthFlowPurpose = Literal["signup", "recovery", "email_change"]


@dataclass(frozen=True)
class AuthFlowRecord:
    purpose: AuthFlowPurpose
    browser_hash: str | None
    code_verifier: str | None = None


def hash_browser_cookie(raw_cookie: str | None) -> str | None:
    """Validate and SHA-256 hash ``shield_auth_browser``; return ``None`` if absent or invalid."""
    if not raw_cookie or not BROWSER_COOKIE_PATTERN.fullmatch(raw_cookie):
        return None
    return hashlib.sha256(raw_cookie.encode("utf-8")).hexdigest()


def browser_cookie_matches(stored_hash: str | None, raw_cookie: str | None) -> bool:
    """Constant-time check that ``raw_cookie`` matches the stored SHA-256 browser hash."""
    if not stored_hash:
        return False
    presented_hash = hash_browser_cookie(raw_cookie)
    if not presented_hash:
        return False
    return hmac.compare_digest(stored_hash, presented_hash)


class AuthFlowStore(Protocol):
    async def create(
        self, record: AuthFlowRecord, *, ttl_seconds: int = SIGNUP_FLOW_TTL_SECONDS
    ) -> str: ...

    async def get(self, flow_id: str) -> AuthFlowRecord | None: ...

    async def delete(self, flow_id: str) -> None: ...


class InMemoryAuthFlowStore:
    """In-memory flow store for development and tests."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._flows: dict[str, AuthFlowRecord] = {}
        self._expiries: dict[str, float] = {}

    def _prune(self) -> None:
        now = self._clock()
        expired = [k for k, exp in self._expiries.items() if exp <= now]
        for key in expired:
            self._expiries.pop(key, None)
            self._flows.pop(key, None)

    async def create(
        self, record: AuthFlowRecord, *, ttl_seconds: int = SIGNUP_FLOW_TTL_SECONDS
    ) -> str:
        self._prune()
        flow_id = secrets.token_urlsafe(24)
        self._flows[flow_id] = record
        self._expiries[flow_id] = self._clock() + ttl_seconds
        return flow_id

    async def get(self, flow_id: str) -> AuthFlowRecord | None:
        self._prune()
        return self._flows.get(flow_id)

    async def delete(self, flow_id: str) -> None:
        self._flows.pop(flow_id, None)
        self._expiries.pop(flow_id, None)


class RedisAuthFlowStore:
    """Redis-backed flow store for multi-instance production deployments."""

    def __init__(self, redis_client: Any, *, clock: Callable[[], float] = time.time) -> None:
        self._redis = redis_client
        self._fallback = InMemoryAuthFlowStore(clock=clock)

    @staticmethod
    def _key(flow_id: str) -> str:
        return f"authflow:{flow_id}"

    async def create(
        self, record: AuthFlowRecord, *, ttl_seconds: int = SIGNUP_FLOW_TTL_SECONDS
    ) -> str:
        flow_id = secrets.token_urlsafe(24)
        payload = json.dumps(
            {
                "purpose": record.purpose,
                "browser_hash": record.browser_hash,
                "code_verifier": record.code_verifier,
            }
        )
        try:
            await self._redis.set(self._key(flow_id), payload, ex=ttl_seconds)
            return flow_id
        except Exception as exc:
            logger.warning(
                "Redis auth flow write failed (%s); using local store", type(exc).__name__
            )
            self._fallback._flows[flow_id] = record
            self._fallback._expiries[flow_id] = self._fallback._clock() + ttl_seconds
            return flow_id

    async def get(self, flow_id: str) -> AuthFlowRecord | None:
        try:
            raw = await self._redis.get(self._key(flow_id))
            if raw is not None:
                data = json.loads(raw)
                return AuthFlowRecord(
                    purpose=data["purpose"],
                    browser_hash=data.get("browser_hash"),
                    code_verifier=data.get("code_verifier"),
                )
        except Exception as exc:
            logger.warning(
                "Redis auth flow read failed (%s); checking local store", type(exc).__name__
            )
        return await self._fallback.get(flow_id)

    async def delete(self, flow_id: str) -> None:
        await self._fallback.delete(flow_id)
        try:
            await self._redis.delete(self._key(flow_id))
        except Exception as exc:
            logger.warning("Redis auth flow delete failed (%s)", type(exc).__name__)
