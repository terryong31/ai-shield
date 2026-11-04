"""Clearance sessions (spec 0012).

The passphrase is checked once, at ``POST /clearance``; afterwards the browser
holds only an opaque token in an ``HttpOnly`` cookie. Only the token's SHA-256
hash is stored, so a leaked database cannot be replayed.
"""

import asyncio
import hashlib
import math
import secrets
import sqlite3
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class SessionStore(Protocol):
    async def create(self, ttl: timedelta) -> tuple[str, datetime]:
        """Start a session; returns the raw token and its expiry."""
        ...

    async def lookup(self, token: str) -> datetime | None:
        """The session's expiry if it is live, otherwise ``None``."""
        ...

    async def revoke(self, token: str) -> None: ...


class InMemorySessionStore:
    """Test double. Lost on restart, so never wired in production."""

    def __init__(self) -> None:
        self._sessions: dict[str, datetime] = {}

    async def create(self, ttl: timedelta) -> tuple[str, datetime]:
        token, expires_at = _new_token(), datetime.now(UTC) + ttl
        self._sessions[_hash(token)] = expires_at
        return token, expires_at

    async def lookup(self, token: str) -> datetime | None:
        expires_at = self._sessions.get(_hash(token))
        return expires_at if expires_at and expires_at > datetime.now(UTC) else None

    async def revoke(self, token: str) -> None:
        self._sessions.pop(_hash(token), None)


class SqliteSessionStore:
    """Sessions in the gateway's SQLite file, so they survive a restart.

    Lives beside the ``requests`` table but is not mirrored to Supabase:
    sessions are gateway-local state (spec 0012, non-goals).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists sessions (
                  token_hash text primary key,
                  created_at text not null,
                  expires_at text not null
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _write(self, sql: str, params: tuple[str, ...]) -> list[tuple[str, ...]]:
        connection = self._connect()
        try:
            with connection:
                return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    async def create(self, ttl: timedelta) -> tuple[str, datetime]:
        token, now = _new_token(), datetime.now(UTC)
        expires_at = now + ttl

        def insert() -> None:
            connection = self._connect()
            try:
                with connection:
                    connection.execute(
                        "delete from sessions where expires_at <= ?", (now.isoformat(),)
                    )
                    connection.execute(
                        "insert into sessions (token_hash, created_at, expires_at)"
                        " values (?, ?, ?)",
                        (_hash(token), now.isoformat(), expires_at.isoformat()),
                    )
            finally:
                connection.close()

        await asyncio.to_thread(insert)
        return token, expires_at

    async def lookup(self, token: str) -> datetime | None:
        rows = await asyncio.to_thread(
            self._write, "select expires_at from sessions where token_hash = ?", (_hash(token),)
        )
        if not rows:
            return None
        expires_at = datetime.fromisoformat(rows[0][0])
        return expires_at if expires_at > datetime.now(UTC) else None

    async def revoke(self, token: str) -> None:
        await asyncio.to_thread(
            self._write, "delete from sessions where token_hash = ?", (_hash(token),)
        )


class AttemptLimiter:
    """Failed ``POST /clearance`` attempts per client address, in a sliding window.

    In-process only: a restart clears it, which is acceptable for one instance.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window: timedelta = timedelta(minutes=10),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_attempts
        self._window = window.total_seconds()
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, client: str) -> deque[float]:
        failures = self._failures.get(client, deque())
        cutoff = self._clock() - self._window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            self._failures.pop(client, None)
        return failures

    def retry_after(self, client: str) -> int | None:
        """Seconds until ``client`` may try again, or ``None`` if it may try now."""
        failures = self._recent(client)
        if len(failures) < self._max:
            return None
        return max(1, math.ceil(failures[0] + self._window - self._clock()))

    def failed_recently(self, client: str) -> bool:
        return bool(self._recent(client))

    def record_failure(self, client: str) -> None:
        self._failures.setdefault(client, deque()).append(self._clock())

    def reset(self, client: str) -> None:
        self._failures.pop(client, None)
