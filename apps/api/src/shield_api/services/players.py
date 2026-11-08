"""Client player authentication, sessions, and daily usage quotas (specs 0016 and 0020)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from shield_api.schemas import PlayerSessionStatus, PlayerTier
from shield_api.services.sqlite import connect_domains

# (wave runs, single-message tests) per UTC day, by tier (spec 0020).
DAILY_LIMITS: dict[PlayerTier, tuple[int, int]] = {
    "anonymous": (1, 3),
    "free": (5, 20),
    "paid": (300, 1000),
}
_MORE_RUNS_HINT: dict[PlayerTier, str] = {
    "anonymous": "Sign in for 5 wave runs a day.",
    "free": "Upgrade to a paid plan for 300 wave runs a day.",
    "paid": "Try again tomorrow.",
}
AI_AGENT_NODE_KINDS: frozenset[str] = frozenset({"safety_check", "agent_review"})


class PlayerAlreadyExistsError(ValueError):
    """Raised when registering an email that already has an account."""


class InvalidCredentialsError(ValueError):
    """Raised when login credentials do not match an account."""


class QuotaExceededError(ValueError):
    """Raised when a player exceeds their tier's daily wave or test quota."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_password(password: str, salt: str) -> str:
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return derived.hex()


def _today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def default_anonymous_status(
    *, authenticated: bool = False, wave_runs_used: int = 0, test_runs_used: int = 0
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


def _build_logged_in_status(
    *,
    email: str,
    player_name: str,
    tier: PlayerTier,
    wave_runs_used: int,
    test_runs_used: int,
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
    )


class PlayerStore(Protocol):
    async def create_anonymous(self, ttl: timedelta) -> tuple[str, PlayerSessionStatus]: ...

    async def register(
        self,
        *,
        email: str,
        password: str,
        player_name: str | None,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]: ...

    async def login(
        self,
        *,
        email: str,
        password: str,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]: ...

    async def lookup(self, token: str | None) -> PlayerSessionStatus: ...

    async def upgrade(self, token: str | None) -> PlayerSessionStatus: ...

    async def check_run(
        self, token: str | None, *, is_custom_test: bool
    ) -> PlayerSessionStatus: ...

    async def consume_run(
        self, token: str | None, *, is_custom_test: bool
    ) -> PlayerSessionStatus: ...

    async def revoke(self, token: str) -> None: ...

    async def load_board(
        self, email: str, level_id: str
    ) -> tuple[dict[str, Any], datetime] | None: ...

    async def save_board(self, email: str, level_id: str, save: dict[str, Any]) -> datetime: ...


@dataclass
class _AccountRecord:
    email: str
    password_hash: str
    salt: str
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
        self._usage: dict[tuple[str, str], tuple[int, int]] = {}
        self._boards: dict[tuple[str, str], tuple[dict[str, Any], datetime]] = {}

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

    async def register(
        self,
        *,
        email: str,
        password: str,
        player_name: str | None,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        if clean_email in self._accounts:
            raise PlayerAlreadyExistsError("An account with this email already exists.")
        name = (player_name or "").strip() or clean_email.split("@")[0]
        salt = secrets.token_hex(16)
        account = _AccountRecord(
            email=clean_email,
            password_hash=_hash_password(password, salt),
            salt=salt,
            player_name=name,
            tier="free",
        )
        self._accounts[clean_email] = account
        token = _new_token()
        self._sessions[_hash_token(token)] = _SessionRecord(
            email=clean_email,
            is_anonymous=False,
            player_name=name,
            tier="free",
            expires_at=datetime.now(UTC) + ttl,
        )
        waves, tests = self._usage.get((clean_email, _today_utc()), (0, 0))
        return token, _build_logged_in_status(
            email=clean_email,
            player_name=name,
            tier="free",
            wave_runs_used=waves,
            test_runs_used=tests,
        )

    async def login(
        self,
        *,
        email: str,
        password: str,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        account = self._accounts.get(clean_email)
        if account is None or not hmac.compare_digest(
            account.password_hash, _hash_password(password, account.salt)
        ):
            raise InvalidCredentialsError("Invalid email or password.")
        token = _new_token()
        self._sessions[_hash_token(token)] = _SessionRecord(
            email=clean_email,
            is_anonymous=False,
            player_name=account.player_name,
            tier=account.tier,
            expires_at=datetime.now(UTC) + ttl,
        )
        waves, tests = self._usage.get((clean_email, _today_utc()), (0, 0))
        return token, _build_logged_in_status(
            email=clean_email,
            player_name=account.player_name,
            tier=account.tier,
            wave_runs_used=waves,
            test_runs_used=tests,
        )

    async def lookup(self, token: str | None) -> PlayerSessionStatus:
        if not token:
            return default_anonymous_status(authenticated=False)
        session = self._sessions.get(_hash_token(token))
        if session is None or session.expires_at <= datetime.now(UTC):
            return default_anonymous_status(authenticated=False)
        if session.is_anonymous or not session.email:
            waves, tests = self._usage.get((_anonymous_usage_key(token), _today_utc()), (0, 0))
            return default_anonymous_status(
                authenticated=True, wave_runs_used=waves, test_runs_used=tests
            )
        account = self._accounts.get(session.email)
        tier = account.tier if account else session.tier
        name = account.player_name if account else session.player_name
        waves, tests = self._usage.get((session.email, _today_utc()), (0, 0))
        return _build_logged_in_status(
            email=session.email,
            player_name=name,
            tier=tier,
            wave_runs_used=waves,
            test_runs_used=tests,
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

    async def consume_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.check_run(token, is_custom_test=is_custom_test)
        usage_key = _usage_key(status, token)
        if usage_key is None:
            return status
        key = (usage_key, _today_utc())
        waves, tests = self._usage.get(key, (0, 0))
        if is_custom_test:
            tests += 1
        else:
            waves += 1
        self._usage[key] = (waves, tests)
        return await self.lookup(token)

    async def revoke(self, token: str) -> None:
        self._sessions.pop(_hash_token(token), None)

    async def load_board(self, email: str, level_id: str) -> tuple[dict[str, Any], datetime] | None:
        found = self._boards.get((email, level_id))
        return (json.loads(json.dumps(found[0])), found[1]) if found else None

    async def save_board(self, email: str, level_id: str, save: dict[str, Any]) -> datetime:
        now = datetime.now(UTC)
        self._boards[(email, level_id)] = (json.loads(json.dumps(save)), now)
        return now


class SqlitePlayerStore:
    """SQLite player accounts, sessions and quotas in the attached ``players`` schema.

    Also creates ``game.saved_boards`` so the SQLite layout mirrors the Postgres
    migrations (API-SCHEMA-006).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists players.accounts (
                  email         text primary key,
                  password_hash text not null,
                  salt          text not null,
                  player_name   text not null,
                  tier          text not null default 'free',
                  created_at    text not null
                );
                create table if not exists players.sessions (
                  token_hash    text primary key,
                  email         text,
                  is_anonymous  integer not null,
                  player_name   text not null,
                  tier          text not null,
                  created_at    text not null,
                  expires_at    text not null
                );
                create table if not exists players.daily_usage (
                  email         text not null,
                  usage_date    text not null,
                  wave_runs     integer not null default 0,
                  test_runs     integer not null default 0,
                  primary key (email, usage_date)
                );
                create table if not exists game.saved_boards (
                  email         text not null,
                  level_id      text not null,
                  save_json     text not null,
                  updated_at    text not null,
                  primary key (email, level_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = connect_domains(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            with conn:
                return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    async def create_anonymous(self, ttl: timedelta) -> tuple[str, PlayerSessionStatus]:
        token = _new_token()
        now = datetime.now(UTC)
        expires_at = now + ttl
        await asyncio.to_thread(
            self._run,
            "insert into players.sessions"
            " (token_hash, email, is_anonymous, player_name, tier, created_at, expires_at)"
            " values (?, ?, 1, 'Anonymous', 'anonymous', ?, ?)",
            (_hash_token(token), None, now.isoformat(), expires_at.isoformat()),
        )
        return token, default_anonymous_status(authenticated=True)

    async def register(
        self,
        *,
        email: str,
        password: str,
        player_name: str | None,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        existing = await asyncio.to_thread(
            self._run,
            "select email from players.accounts where email = ?",
            (clean_email,),
        )
        if existing:
            raise PlayerAlreadyExistsError("An account with this email already exists.")
        name = (player_name or "").strip() or clean_email.split("@")[0]
        salt = secrets.token_hex(16)
        now = datetime.now(UTC)
        expires_at = now + ttl
        token = _new_token()
        await asyncio.to_thread(
            self._run,
            "insert into players.accounts"
            " (email, password_hash, salt, player_name, tier, created_at)"
            " values (?, ?, ?, ?, 'free', ?)",
            (clean_email, _hash_password(password, salt), salt, name, now.isoformat()),
        )
        await asyncio.to_thread(
            self._run,
            "insert into players.sessions"
            " (token_hash, email, is_anonymous, player_name, tier, created_at, expires_at)"
            " values (?, ?, 0, ?, 'free', ?, ?)",
            (_hash_token(token), clean_email, name, now.isoformat(), expires_at.isoformat()),
        )
        return token, _build_logged_in_status(
            email=clean_email,
            player_name=name,
            tier="free",
            wave_runs_used=0,
            test_runs_used=0,
        )

    async def login(
        self,
        *,
        email: str,
        password: str,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        rows = await asyncio.to_thread(
            self._run,
            "select * from players.accounts where email = ?",
            (clean_email,),
        )
        if not rows:
            raise InvalidCredentialsError("Invalid email or password.")
        account = rows[0]
        if not hmac.compare_digest(
            str(account["password_hash"]), _hash_password(password, str(account["salt"]))
        ):
            raise InvalidCredentialsError("Invalid email or password.")
        now = datetime.now(UTC)
        expires_at = now + ttl
        token = _new_token()
        tier: PlayerTier = "paid" if str(account["tier"]) == "paid" else "free"
        name = str(account["player_name"])
        await asyncio.to_thread(
            self._run,
            "insert into players.sessions"
            " (token_hash, email, is_anonymous, player_name, tier, created_at, expires_at)"
            " values (?, ?, 0, ?, ?, ?, ?)",
            (_hash_token(token), clean_email, name, tier, now.isoformat(), expires_at.isoformat()),
        )
        return token, await self.lookup(token)

    async def lookup(self, token: str | None) -> PlayerSessionStatus:
        if not token:
            return default_anonymous_status(authenticated=False)
        rows = await asyncio.to_thread(
            self._run,
            "select * from players.sessions where token_hash = ?",
            (_hash_token(token),),
        )
        if not rows:
            return default_anonymous_status(authenticated=False)
        session = rows[0]
        if datetime.fromisoformat(str(session["expires_at"])) <= datetime.now(UTC):
            return default_anonymous_status(authenticated=False)
        if bool(session["is_anonymous"]) or not session["email"]:
            waves, tests = await self._usage(_anonymous_usage_key(token))
            return default_anonymous_status(
                authenticated=True, wave_runs_used=waves, test_runs_used=tests
            )
        email = str(session["email"])
        acc_rows = await asyncio.to_thread(
            self._run,
            "select player_name, tier from players.accounts where email = ?",
            (email,),
        )
        raw_tier = str(acc_rows[0]["tier"]) if acc_rows else str(session["tier"])
        tier: PlayerTier = "paid" if raw_tier == "paid" else "free"
        name = str(acc_rows[0]["player_name"]) if acc_rows else str(session["player_name"])
        waves, tests = await self._usage(email)
        return _build_logged_in_status(
            email=email,
            player_name=name,
            tier=tier,
            wave_runs_used=waves,
            test_runs_used=tests,
        )

    async def upgrade(self, token: str | None) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if status.is_anonymous or not status.email or not token:
            raise PermissionError("Sign in required to upgrade plan.")
        await asyncio.to_thread(
            self._run,
            "update players.accounts set tier = 'paid' where email = ?",
            (status.email,),
        )
        await asyncio.to_thread(
            self._run,
            "update players.sessions set tier = 'paid' where token_hash = ?",
            (_hash_token(token),),
        )
        return await self.lookup(token)

    async def _usage(self, usage_key: str) -> tuple[int, int]:
        rows = await asyncio.to_thread(
            self._run,
            "select wave_runs, test_runs from players.daily_usage"
            " where email = ? and usage_date = ?",
            (usage_key, _today_utc()),
        )
        if not rows:
            return 0, 0
        return int(rows[0]["wave_runs"]), int(rows[0]["test_runs"])

    async def check_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if _usage_key(status, token) is not None:
            ensure_run_allowed(status, is_custom_test=is_custom_test)
        return status

    async def consume_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.check_run(token, is_custom_test=is_custom_test)
        usage_key = _usage_key(status, token)
        if usage_key is None:
            return status
        today = _today_utc()
        wave_inc = 0 if is_custom_test else 1
        test_inc = 1 if is_custom_test else 0
        await asyncio.to_thread(
            self._run,
            """
            insert into players.daily_usage (email, usage_date, wave_runs, test_runs)
            values (?, ?, ?, ?)
            on conflict(email, usage_date) do update set
              wave_runs = wave_runs + excluded.wave_runs,
              test_runs = test_runs + excluded.test_runs
            """,
            (usage_key, today, wave_inc, test_inc),
        )
        return await self.lookup(token)

    async def revoke(self, token: str) -> None:
        await asyncio.to_thread(
            self._run,
            "delete from players.sessions where token_hash = ?",
            (_hash_token(token),),
        )

    async def load_board(self, email: str, level_id: str) -> tuple[dict[str, Any], datetime] | None:
        rows = await asyncio.to_thread(
            self._run,
            "select save_json, updated_at from game.saved_boards where email = ? and level_id = ?",
            (email, level_id),
        )
        if not rows:
            return None
        return json.loads(rows[0]["save_json"]), datetime.fromisoformat(rows[0]["updated_at"])

    async def save_board(self, email: str, level_id: str, save: dict[str, Any]) -> datetime:
        now = datetime.now(UTC)
        await asyncio.to_thread(
            self._run,
            """
            insert into game.saved_boards (email, level_id, save_json, updated_at)
            values (?, ?, ?, ?)
            on conflict(email, level_id) do update set
              save_json = excluded.save_json,
              updated_at = excluded.updated_at
            """,
            (email, level_id, json.dumps(save), now.isoformat()),
        )
        return now


class SupabasePlayerStore:
    """Player accounts, sessions and quotas in the Supabase ``players`` schema (spec 0024).

    Stores only SHA-256 session token hashes and PBKDF2 password hashes. The
    supabase-py client is synchronous, so every call runs in a worker thread.
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

    def _usage(self, usage_key: str) -> tuple[int, int]:
        rows = (
            self._table(self.USAGE_TABLE)
            .select("wave_runs,test_runs")
            .eq("email", usage_key)
            .eq("usage_date", _today_utc())
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return 0, 0
        return int(rows[0]["wave_runs"]), int(rows[0]["test_runs"])

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
            waves, tests = self._usage(_anonymous_usage_key(token))
            return default_anonymous_status(
                authenticated=True, wave_runs_used=waves, test_runs_used=tests
            )
        email = str(session["email"])
        account = self._account(email)
        raw_tier = str(account["tier"]) if account else str(session["tier"])
        tier: PlayerTier = "paid" if raw_tier == "paid" else "free"
        name = str(account["player_name"]) if account else str(session["player_name"])
        waves, tests = self._usage(email)
        return _build_logged_in_status(
            email=email, player_name=name, tier=tier, wave_runs_used=waves, test_runs_used=tests
        )

    async def create_anonymous(self, ttl: timedelta) -> tuple[str, PlayerSessionStatus]:
        token = _new_token()
        await asyncio.to_thread(
            self._insert_session, token, email=None, name="Anonymous", tier="anonymous", ttl=ttl
        )
        return token, default_anonymous_status(authenticated=True)

    async def register(
        self,
        *,
        email: str,
        password: str,
        player_name: str | None,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        name = (player_name or "").strip() or clean_email.split("@")[0]

        def write() -> str:
            if self._account(clean_email) is not None:
                raise PlayerAlreadyExistsError("An account with this email already exists.")
            salt = secrets.token_hex(16)
            self._table(self.ACCOUNTS_TABLE).insert(
                {
                    "email": clean_email,
                    "password_hash": _hash_password(password, salt),
                    "salt": salt,
                    "player_name": name,
                    "tier": "free",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
            token = _new_token()
            self._insert_session(token, email=clean_email, name=name, tier="free", ttl=ttl)
            return token

        token = await asyncio.to_thread(write)
        return token, await self.lookup(token)

    async def login(
        self,
        *,
        email: str,
        password: str,
        ttl: timedelta,
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()

        def write() -> str:
            account = self._account(clean_email)
            if account is None or not hmac.compare_digest(
                str(account["password_hash"]), _hash_password(password, str(account["salt"]))
            ):
                raise InvalidCredentialsError("Invalid email or password.")
            tier: PlayerTier = "paid" if str(account["tier"]) == "paid" else "free"
            token = _new_token()
            self._insert_session(
                token, email=clean_email, name=str(account["player_name"]), tier=tier, ttl=ttl
            )
            return token

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

    async def check_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.lookup(token)
        if _usage_key(status, token) is not None:
            ensure_run_allowed(status, is_custom_test=is_custom_test)
        return status

    async def consume_run(self, token: str | None, *, is_custom_test: bool) -> PlayerSessionStatus:
        status = await self.check_run(token, is_custom_test=is_custom_test)
        usage_key = _usage_key(status, token)
        if usage_key is None:
            return status

        def write() -> None:
            # Read-then-upsert: PostgREST has no atomic increment without an RPC. Two
            # concurrent runs can undercount by one, which only ever favours the player.
            waves, tests = self._usage(usage_key)
            self._table(self.USAGE_TABLE).upsert(
                {
                    "email": usage_key,
                    "usage_date": _today_utc(),
                    "wave_runs": waves + (0 if is_custom_test else 1),
                    "test_runs": tests + (1 if is_custom_test else 0),
                },
                on_conflict="email,usage_date",
            ).execute()

        await asyncio.to_thread(write)
        return await self.lookup(token)

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
