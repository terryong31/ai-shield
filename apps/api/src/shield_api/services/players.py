"""Client player authentication, sessions, and daily usage quotas (specs 0016, 0020, 0045)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from shield_api.schemas import PlayerSessionStatus, PlayerTier

# (wave runs, single-message tests) per UTC day, by tier (spec 0020).
DAILY_LIMITS: dict[PlayerTier, tuple[int, int]] = {
    "anonymous": (1, 3),
    "free": (5, 20),
    "paid": (300, 1000),
}
DAILY_TRAIN_LIMITS: dict[PlayerTier, int] = {
    "anonymous": 0,
    "free": 3,
    "paid": 200,
}
_MORE_RUNS_HINT: dict[PlayerTier, str] = {
    "anonymous": "Sign in for 5 wave runs a day.",
    "free": "Upgrade to a paid plan for 300 wave runs a day.",
    "paid": "Try again tomorrow.",
}
AI_AGENT_NODE_KINDS: frozenset[str] = frozenset({"safety_check", "llm_review"})


class QuotaExceededError(ValueError):
    """Raised when a player exceeds their tier's daily wave, test, or train quota."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _profile_name(email: str, player_name: str | None) -> str:
    return (player_name or "").strip() or email.split("@")[0]


def _today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def default_anonymous_status(
    *,
    authenticated: bool = False,
    wave_runs_used: int = 0,
    test_runs_used: int = 0,
    train_runs_used: int = 0,
) -> PlayerSessionStatus:
    wave_limit, test_limit = DAILY_LIMITS["anonymous"]
    return PlayerSessionStatus(
        authenticated=authenticated,
        is_anonymous=True,
        tier="anonymous",
        email=None,
        player_name="Anonymous",
        ai_nodes_allowed=False,
        can_record_scores=False,
        daily_wave_limit=wave_limit,
        wave_runs_used=wave_runs_used,
        daily_test_limit=test_limit,
        test_runs_used=test_runs_used,
        daily_train_limit=DAILY_TRAIN_LIMITS["anonymous"],
        train_runs_used=train_runs_used,
    )


def _anonymous_usage_key(token: str) -> str:
    # Anonymous sessions have no email, so usage is keyed by the hashed session token.
    return f"anon:{_hash_token(token)}"


def _usage_key(status: PlayerSessionStatus, token: str | None) -> str | None:
    """Who a run is charged to; ``None`` means there is no session to count against."""
    if not token or not status.authenticated:
        return None
    if status.is_anonymous or not status.email:
        return _anonymous_usage_key(token)
    return status.email


def ensure_run_allowed(status: PlayerSessionStatus, *, is_custom_test: bool) -> None:
    """Raise :class:`QuotaExceededError` when the player has no runs of this kind left today."""
    if is_custom_test:
        used, limit, kind = status.test_runs_used, status.daily_test_limit, "test"
    else:
        used, limit, kind = status.wave_runs_used, status.daily_wave_limit, "wave"
    if limit is not None and used >= limit:
        raise QuotaExceededError(
            f"Daily {kind} limit ({limit}/{limit}) reached. {_MORE_RUNS_HINT[status.tier]}"
        )


def ensure_train_allowed(status: PlayerSessionStatus) -> None:
    """Raise :class:`QuotaExceededError` when a signed-in player hits their daily train limit."""
    limit = status.daily_train_limit
    if limit is not None and status.train_runs_used >= limit:
        raise QuotaExceededError(
            f"Daily training limit ({limit}/{limit}) reached. {_MORE_RUNS_HINT[status.tier]}"
        )


def _build_logged_in_status(
    *,
    email: str,
    player_name: str,
    tier: PlayerTier,
    wave_runs_used: int,
    test_runs_used: int,
    train_runs_used: int = 0,
) -> PlayerSessionStatus:
    wave_limit, test_limit = DAILY_LIMITS[tier]
    return PlayerSessionStatus(
        authenticated=True,
        is_anonymous=False,
        tier=tier,
        email=email,
        player_name=player_name,
        ai_nodes_allowed=True,
        can_record_scores=True,
        daily_wave_limit=wave_limit,
        wave_runs_used=wave_runs_used,
        daily_test_limit=test_limit,
        test_runs_used=test_runs_used,
        daily_train_limit=DAILY_TRAIN_LIMITS[tier],
        train_runs_used=train_runs_used,
    )


class PlayerStore(Protocol):
    async def create_anonymous(self, ttl: timedelta) -> tuple[str, PlayerSessionStatus]: ...

    async def sign_in_verified(
        self, *, email: str, player_name: str | None, ttl: timedelta
    ) -> tuple[str, PlayerSessionStatus]:
        """Open a session for an email Supabase Auth has verified (spec 0027)."""
        ...

    async def lookup(self, token: str | None) -> PlayerSessionStatus: ...

    async def upgrade(self, token: str | None) -> PlayerSessionStatus: ...

    async def check_run(
        self, token: str | None, *, is_custom_test: bool
    ) -> PlayerSessionStatus: ...

    async def consume_run(
        self, token: str | None, *, is_custom_test: bool
    ) -> PlayerSessionStatus: ...

    async def reserve_run(
        self, token: str | None, *, is_custom_test: bool
    ) -> PlayerSessionStatus: ...

    async def release_run(
        self, token: str | None, *, is_custom_test: bool
    ) -> PlayerSessionStatus: ...

    async def check_train(self, token: str | None) -> PlayerSessionStatus: ...

    async def consume_train(self, token: str | None) -> PlayerSessionStatus: ...

    async def reserve_train(self, token: str | None) -> PlayerSessionStatus: ...

    async def release_train(self, token: str | None) -> PlayerSessionStatus: ...

    async def revoke(self, token: str) -> None: ...

    async def load_board(
        self, email: str, level_id: str
    ) -> tuple[dict[str, Any], datetime] | None: ...

    async def save_board(self, email: str, level_id: str, save: dict[str, Any]) -> datetime: ...

    # Account settings (spec 0025). Emails are already trimmed and lower-cased.

    async def revoke_sessions(self, email: str, *, keep: str | None) -> None:
        """End every session of this account except the one with token ``keep``."""
        ...

    async def email_taken(self, email: str) -> bool: ...

    async def move_email(self, old: str, new: str) -> None:
        """Move boards, usage (keeping the larger count per day), sessions, then the account."""
        ...

    async def delete_boards(self, email: str) -> int: ...

    async def delete_account(self, email: str) -> None:
        """Delete sessions, then the account. Usage rows are kept (spec 0025)."""
        ...


@dataclass
class _AccountRecord:
    email: str
    player_name: str
    tier: PlayerTier


@dataclass
class _SessionRecord:
    email: str | None
    is_anonymous: bool
    player_name: str
    tier: PlayerTier
    expires_at: datetime


class InMemoryPlayerStore:
    """In-memory player store for tests."""

    def __init__(self) -> None:
        self._accounts: dict[str, _AccountRecord] = {}
        self._sessions: dict[str, _SessionRecord] = {}
        self._usage: dict[tuple[str, str], tuple[int, int, int]] = {}
        self._boards: dict[tuple[str, str], tuple[dict[str, Any], datetime]] = {}
        self._lock = asyncio.Lock()

    async def create_anonymous(self, ttl: timedelta) -> tuple[str, PlayerSessionStatus]:
        token = _new_token()
        self._sessions[_hash_token(token)] = _SessionRecord(
            email=None,
            is_anonymous=True,
            player_name="Anonymous",
            tier="anonymous",
            expires_at=datetime.now(UTC) + ttl,
        )
        return token, default_anonymous_status(authenticated=True)

    def _open(self, account: _AccountRecord, ttl: timedelta) -> tuple[str, PlayerSessionStatus]:
        clean_email = account.email
        token = _new_token()
        self._sessions[_hash_token(token)] = _SessionRecord(
            email=clean_email,
            is_anonymous=False,
            player_name=account.player_name,
            tier=account.tier,
            expires_at=datetime.now(UTC) + ttl,
        )
        waves, tests, trains = self._usage.get((clean_email, _today_utc()), (0, 0, 0))
        return token, _build_logged_in_status(
            email=clean_email,
            player_name=account.player_name,
            tier=account.tier,
            wave_runs_used=waves,
            test_runs_used=tests,
            train_runs_used=trains,
        )

    async def sign_in_verified(
        self, *, email: str, player_name: str | None, ttl: timedelta
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        account = self._accounts.get(clean_email)
        if account is None:
            account = _AccountRecord(
                email=clean_email,
                player_name=_profile_name(clean_email, player_name),
                tier="free",
            )
            self._accounts[clean_email] = account
        return self._open(account, ttl)

    async def lookup(self, token: str | None) -> PlayerSessionStatus:
        if not token:
            return default_anonymous_status(authenticated=False)
        session = self._sessions.get(_hash_token(token))
        if session is None or session.expires_at <= datetime.now(UTC):
            return default_anonymous_status(authenticated=False)
        if session.is_anonymous or not session.email:
            waves, tests, _ = self._usage.get(
                (_anonymous_usage_key(token), _today_utc()), (0, 0, 0)
            )
            return default_anonymous_status(
                authenticated=True, wave_runs_used=waves, test_runs_used=tests
            )
        account = self._accounts.get(session.email)
        tier = account.tier if account else session.tier
        name = account.player_name if account else session.player_name
        waves, tests, trains = self._usage.get((session.email, _today_utc()), (0, 0, 0))
        return _build_logged_in_status(
            email=session.email,
            player_name=name,
            tier=tier,
            wave_runs_used=waves,
            test_runs_used=tests,
            train_runs_used=trains,
        )

    async def upgrade(self, token: str | None) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if status.is_anonymous or not status.email or not token:
            raise PermissionError("Sign in required to upgrade plan.")
        account = self._accounts.get(status.email)
        if account:
            account.tier = "paid"
        session = self._sessions.get(_hash_token(token))
        if session:
            session.tier = "paid"
        return await self.lookup(token)

    async def check_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if _usage_key(status, token) is not None:
            ensure_run_allowed(status, is_custom_test=is_custom_test)
        return status

    async def _mutate_usage_in_memory(
        self, usage_key: str, *, kind: str, delta: int
    ) -> tuple[int, int, int]:
        key = (usage_key, _today_utc())
        waves, tests, trains = self._usage.get(key, (0, 0, 0))
        if kind == "wave":
            waves = max(0, waves + delta)
        elif kind == "test":
            tests = max(0, tests + delta)
        else:
            trains = max(0, trains + delta)
        self._usage[key] = (waves, tests, trains)
        return waves, tests, trains

    async def reserve_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        async with self._lock:
            status = await self.check_run(token, is_custom_test=is_custom_test)
            usage_key = _usage_key(status, token)
            if usage_key is None:
                return status
            kind = "test" if is_custom_test else "wave"
            waves, tests, trains = await self._mutate_usage_in_memory(usage_key, kind=kind, delta=1)
            return status.model_copy(
                update={
                    "wave_runs_used": waves,
                    "test_runs_used": tests,
                    "train_runs_used": trains,
                }
            )

    async def release_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        async with self._lock:
            status = await self.lookup(token)
            usage_key = _usage_key(status, token)
            if usage_key is None:
                return status
            kind = "test" if is_custom_test else "wave"
            waves, tests, trains = await self._mutate_usage_in_memory(
                usage_key, kind=kind, delta=-1
            )
            return status.model_copy(
                update={
                    "wave_runs_used": waves,
                    "test_runs_used": tests,
                    "train_runs_used": trains,
                }
            )

    async def consume_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        return await self.reserve_run(token, is_custom_test=is_custom_test)

    async def check_train(self, token: str | None) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if not status.authenticated or status.is_anonymous or not status.email:
            raise PermissionError("Sign in to train the ML filter.")
        ensure_train_allowed(status)
        return status

    async def reserve_train(self, token: str | None) -> PlayerSessionStatus:
        async with self._lock:
            status = await self.check_train(token)
            assert status.email is not None
            waves, tests, trains = await self._mutate_usage_in_memory(
                status.email, kind="train", delta=1
            )
            return status.model_copy(
                update={
                    "wave_runs_used": waves,
                    "test_runs_used": tests,
                    "train_runs_used": trains,
                }
            )

    async def release_train(self, token: str | None) -> PlayerSessionStatus:
        async with self._lock:
            status = await self.lookup(token)
            if not status.authenticated or status.is_anonymous or not status.email:
                return status
            waves, tests, trains = await self._mutate_usage_in_memory(
                status.email, kind="train", delta=-1
            )
            return status.model_copy(
                update={
                    "wave_runs_used": waves,
                    "test_runs_used": tests,
                    "train_runs_used": trains,
                }
            )

    async def consume_train(self, token: str | None) -> PlayerSessionStatus:
        return await self.reserve_train(token)

    async def revoke(self, token: str) -> None:
        self._sessions.pop(_hash_token(token), None)

    async def load_board(self, email: str, level_id: str) -> tuple[dict[str, Any], datetime] | None:
        found = self._boards.get((email, level_id))
        return (json.loads(json.dumps(found[0])), found[1]) if found else None

    async def save_board(self, email: str, level_id: str, save: dict[str, Any]) -> datetime:
        now = datetime.now(UTC)
        self._boards[(email, level_id)] = (json.loads(json.dumps(save)), now)
        return now

    async def revoke_sessions(self, email: str, *, keep: str | None) -> None:
        keep_hash = _hash_token(keep) if keep else None
        for token_hash in [
            h for h, session in self._sessions.items() if session.email == email and h != keep_hash
        ]:
            del self._sessions[token_hash]

    async def email_taken(self, email: str) -> bool:
        return email in self._accounts

    async def move_email(self, old: str, new: str) -> None:
        for email, level_id in [key for key in self._boards if key[0] == old]:
            self._boards[(new, level_id)] = self._boards.pop((email, level_id))
        for email, day in [key for key in self._usage if key[0] == old]:
            waves, tests, trains = self._usage.pop((email, day))
            other_waves, other_tests, other_trains = self._usage.get((new, day), (0, 0, 0))
            self._usage[(new, day)] = (
                max(waves, other_waves),
                max(tests, other_tests),
                max(trains, other_trains),
            )
        for session in self._sessions.values():
            if session.email == old:
                session.email = new
        account = self._accounts.pop(old)
        account.email = new
        self._accounts[new] = account

    async def delete_boards(self, email: str) -> int:
        keys = [key for key in self._boards if key[0] == email]
        for key in keys:
            del self._boards[key]
        return len(keys)

    async def delete_account(self, email: str) -> None:
        await self.revoke_sessions(email, keep=None)
        self._accounts.pop(email, None)


class SupabasePlayerStore:
    """Player accounts, sessions and quotas in the Supabase ``players`` schema (spec 0024).

    Stores only SHA-256 session token hashes; Supabase Auth owns passwords.
    The supabase-py client is synchronous, so every call runs in a worker thread.
    """

    SCHEMA = "players"
    ACCOUNTS_TABLE = "accounts"
    SESSIONS_TABLE = "sessions"
    USAGE_TABLE = "daily_usage"
    BOARDS_SCHEMA = "game"
    BOARDS_TABLE = "saved_boards"

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self, name: str) -> Any:
        return self._client.schema(self.SCHEMA).table(name)

    def _account(self, email: str) -> dict[str, Any] | None:
        rows = (
            self._table(self.ACCOUNTS_TABLE).select("*").eq("email", email).limit(1).execute().data
        )
        return dict(rows[0]) if rows else None

    def _usage(self, usage_key: str) -> tuple[int, int, int]:
        rows = (
            self._table(self.USAGE_TABLE)
            .select("*")
            .eq("email", usage_key)
            .eq("usage_date", _today_utc())
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return 0, 0, 0
        row = rows[0]
        return (
            int(row.get("wave_runs", 0)),
            int(row.get("test_runs", 0)),
            int(row.get("train_runs", 0)),
        )

    def _insert_session(
        self, token: str, *, email: str | None, name: str, tier: PlayerTier, ttl: timedelta
    ) -> None:
        now = datetime.now(UTC)
        self._table(self.SESSIONS_TABLE).insert(
            {
                "token_hash": _hash_token(token),
                "email": email,
                "is_anonymous": email is None,
                "player_name": name,
                "tier": tier,
                "created_at": now.isoformat(),
                "expires_at": (now + ttl).isoformat(),
            }
        ).execute()

    def _lookup(self, token: str | None) -> PlayerSessionStatus:
        if not token:
            return default_anonymous_status(authenticated=False)
        rows = (
            self._table(self.SESSIONS_TABLE)
            .select("*")
            .eq("token_hash", _hash_token(token))
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return default_anonymous_status(authenticated=False)
        session = rows[0]
        if datetime.fromisoformat(str(session["expires_at"])) <= datetime.now(UTC):
            return default_anonymous_status(authenticated=False)
        if bool(session["is_anonymous"]) or not session["email"]:
            waves, tests, _ = self._usage(_anonymous_usage_key(token))
            return default_anonymous_status(
                authenticated=True, wave_runs_used=waves, test_runs_used=tests
            )
        email = str(session["email"])
        account = self._account(email)
        raw_tier = str(account["tier"]) if account else str(session["tier"])
        tier: PlayerTier = "paid" if raw_tier == "paid" else "free"
        name = str(account["player_name"]) if account else str(session["player_name"])
        waves, tests, trains = self._usage(email)
        return _build_logged_in_status(
            email=email,
            player_name=name,
            tier=tier,
            wave_runs_used=waves,
            test_runs_used=tests,
            train_runs_used=trains,
        )

    async def create_anonymous(self, ttl: timedelta) -> tuple[str, PlayerSessionStatus]:
        token = _new_token()
        await asyncio.to_thread(
            self._insert_session, token, email=None, name="Anonymous", tier="anonymous", ttl=ttl
        )
        return token, default_anonymous_status(authenticated=True)

    def _open(self, account: dict[str, Any], ttl: timedelta) -> str:
        tier: PlayerTier = "paid" if str(account["tier"]) == "paid" else "free"
        token = _new_token()
        self._insert_session(
            token, email=str(account["email"]), name=str(account["player_name"]), tier=tier, ttl=ttl
        )
        return token

    async def sign_in_verified(
        self, *, email: str, player_name: str | None, ttl: timedelta
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()

        def write() -> str:
            account = self._account(clean_email)
            if account is None:
                account = {
                    "email": clean_email,
                    "player_name": _profile_name(clean_email, player_name),
                    "tier": "free",
                    "created_at": datetime.now(UTC).isoformat(),
                }
                self._table(self.ACCOUNTS_TABLE).insert(account).execute()
            return self._open(account, ttl)

        token = await asyncio.to_thread(write)
        return token, await self.lookup(token)

    async def lookup(self, token: str | None) -> PlayerSessionStatus:
        return await asyncio.to_thread(self._lookup, token)

    async def upgrade(self, token: str | None) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if status.is_anonymous or not status.email or not token:
            raise PermissionError("Sign in required to upgrade plan.")
        email = status.email

        def write() -> None:
            self._table(self.ACCOUNTS_TABLE).update({"tier": "paid"}).eq("email", email).execute()
            self._table(self.SESSIONS_TABLE).update({"tier": "paid"}).eq(
                "token_hash", _hash_token(token)
            ).execute()

        await asyncio.to_thread(write)
        return await self.lookup(token)

    def _reserve_usage_rpc(
        self, usage_key: str, *, kind: str, limit: int
    ) -> tuple[bool, int, int, int]:
        rows = (
            self._client.schema(self.SCHEMA)
            .rpc(
                "reserve_daily_usage",
                {
                    "p_email": usage_key,
                    "p_usage_date": _today_utc(),
                    "p_kind": kind,
                    "p_limit": limit,
                },
            )
            .execute()
            .data
            or []
        )
        if not rows:
            return False, 0, 0, 0
        row = rows[0]
        return (
            bool(row.get("reserved", False)),
            int(row.get("wave_runs", 0)),
            int(row.get("test_runs", 0)),
            int(row.get("train_runs", 0)),
        )

    def _release_usage_rpc(self, usage_key: str, *, kind: str) -> tuple[int, int, int]:
        rows = (
            self._client.schema(self.SCHEMA)
            .rpc(
                "release_daily_usage",
                {
                    "p_email": usage_key,
                    "p_usage_date": _today_utc(),
                    "p_kind": kind,
                },
            )
            .execute()
            .data
            or []
        )
        if not rows:
            return 0, 0, 0
        row = rows[0]
        return (
            int(row.get("wave_runs", 0)),
            int(row.get("test_runs", 0)),
            int(row.get("train_runs", 0)),
        )

    async def check_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if _usage_key(status, token) is not None:
            ensure_run_allowed(status, is_custom_test=is_custom_test)
        return status

    async def reserve_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.lookup(token)
        usage_key = _usage_key(status, token)
        if usage_key is None:
            return status
        kind = "test" if is_custom_test else "wave"
        limit = status.daily_test_limit if is_custom_test else status.daily_wave_limit
        if limit is None:
            return status
        reserved, waves, tests, trains = await asyncio.to_thread(
            self._reserve_usage_rpc, usage_key, kind=kind, limit=limit
        )
        updated = status.model_copy(
            update={
                "wave_runs_used": waves,
                "test_runs_used": tests,
                "train_runs_used": trains,
            }
        )
        if not reserved:
            raise QuotaExceededError(
                f"Daily {kind} limit ({limit}/{limit}) reached. {_MORE_RUNS_HINT[status.tier]}"
            )
        return updated

    async def release_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.lookup(token)
        usage_key = _usage_key(status, token)
        if usage_key is None:
            return status
        kind = "test" if is_custom_test else "wave"
        waves, tests, trains = await asyncio.to_thread(
            self._release_usage_rpc, usage_key, kind=kind
        )
        return status.model_copy(
            update={
                "wave_runs_used": waves,
                "test_runs_used": tests,
                "train_runs_used": trains,
            }
        )

    async def consume_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        return await self.reserve_run(token, is_custom_test=is_custom_test)

    async def check_train(self, token: str | None) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if not status.authenticated or status.is_anonymous or not status.email:
            raise PermissionError("Sign in to train the ML filter.")
        ensure_train_allowed(status)
        return status

    async def reserve_train(self, token: str | None) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if not status.authenticated or status.is_anonymous or not status.email:
            raise PermissionError("Sign in to train the ML filter.")
        limit = status.daily_train_limit
        if limit is None:
            return status
        reserved, waves, tests, trains = await asyncio.to_thread(
            self._reserve_usage_rpc, status.email, kind="train", limit=limit
        )
        updated = status.model_copy(
            update={
                "wave_runs_used": waves,
                "test_runs_used": tests,
                "train_runs_used": trains,
            }
        )
        if not reserved:
            raise QuotaExceededError(
                f"Daily training limit ({limit}/{limit}) reached. {_MORE_RUNS_HINT[status.tier]}"
            )
        return updated

    async def release_train(self, token: str | None) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if not status.authenticated or status.is_anonymous or not status.email:
            return status
        waves, tests, trains = await asyncio.to_thread(
            self._release_usage_rpc, status.email, kind="train"
        )
        return status.model_copy(
            update={
                "wave_runs_used": waves,
                "test_runs_used": tests,
                "train_runs_used": trains,
            }
        )

    async def consume_train(self, token: str | None) -> PlayerSessionStatus:
        return await self.reserve_train(token)

    def _boards(self) -> Any:
        return self._client.schema(self.BOARDS_SCHEMA).table(self.BOARDS_TABLE)

    async def load_board(self, email: str, level_id: str) -> tuple[dict[str, Any], datetime] | None:
        response = await asyncio.to_thread(
            lambda: (
                self._boards()
                .select("save_json,updated_at")
                .eq("email", email)
                .eq("level_id", level_id)
                .limit(1)
                .execute()
            )
        )
        rows = response.data or []
        if not rows:
            return None
        raw = rows[0]["save_json"]
        save = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return save, datetime.fromisoformat(str(rows[0]["updated_at"]))

    async def save_board(self, email: str, level_id: str, save: dict[str, Any]) -> datetime:
        now = datetime.now(UTC)
        row = {
            "email": email,
            "level_id": level_id,
            "save_json": save,
            "updated_at": now.isoformat(),
        }
        await asyncio.to_thread(
            lambda: self._boards().upsert(row, on_conflict="email,level_id").execute()
        )
        return now

    async def revoke(self, token: str) -> None:
        await asyncio.to_thread(
            lambda: (
                self._table(self.SESSIONS_TABLE)
                .delete()
                .eq("token_hash", _hash_token(token))
                .execute()
            )
        )

    async def revoke_sessions(self, email: str, *, keep: str | None) -> None:
        def write() -> None:
            query = self._table(self.SESSIONS_TABLE).delete().eq("email", email)
            if keep:
                query = query.neq("token_hash", _hash_token(keep))
            query.execute()

        await asyncio.to_thread(write)

    async def email_taken(self, email: str) -> bool:
        return await asyncio.to_thread(self._account, email) is not None

    async def move_email(self, old: str, new: str) -> None:
        # Separate PostgREST calls with no transaction: dependents first, the account
        # row last, so a failure midway leaves the old login working (spec 0025).
        def write() -> None:
            self._boards().update({"email": new}).eq("email", old).execute()
            old_usage = (
                self._table(self.USAGE_TABLE).select("*").eq("email", old).execute().data or []
            )
            for row in old_usage:
                existing = (
                    self._table(self.USAGE_TABLE)
                    .select("*")
                    .eq("email", new)
                    .eq("usage_date", row["usage_date"])
                    .limit(1)
                    .execute()
                    .data
                )
                other = (
                    existing[0] if existing else {"wave_runs": 0, "test_runs": 0, "train_runs": 0}
                )
                self._table(self.USAGE_TABLE).upsert(
                    {
                        "email": new,
                        "usage_date": row["usage_date"],
                        "wave_runs": max(
                            int(row.get("wave_runs", 0)), int(other.get("wave_runs", 0))
                        ),
                        "test_runs": max(
                            int(row.get("test_runs", 0)), int(other.get("test_runs", 0))
                        ),
                        "train_runs": max(
                            int(row.get("train_runs", 0)), int(other.get("train_runs", 0))
                        ),
                    },
                    on_conflict="email,usage_date",
                ).execute()
            self._table(self.USAGE_TABLE).delete().eq("email", old).execute()
            self._table(self.SESSIONS_TABLE).update({"email": new}).eq("email", old).execute()
            self._table(self.ACCOUNTS_TABLE).update({"email": new}).eq("email", old).execute()

        await asyncio.to_thread(write)

    async def delete_boards(self, email: str) -> int:
        response = await asyncio.to_thread(
            lambda: self._boards().delete().eq("email", email).execute()
        )
        return len(response.data or [])

    async def delete_account(self, email: str) -> None:
        def write() -> None:
            self._table(self.SESSIONS_TABLE).delete().eq("email", email).execute()
            self._table(self.ACCOUNTS_TABLE).delete().eq("email", email).execute()

        await asyncio.to_thread(write)
