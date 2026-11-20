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
AI_AGENT_NODE_KINDS: frozenset[str] = frozenset({"safety_check", "llm_review"})


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


def _password_matches(password: str, password_hash: object, salt: object) -> bool:
    """Local (development) password check. Profiles owned by Supabase Auth have no hash."""
    if not isinstance(password_hash, str) or not isinstance(salt, str):
        return False
    return hmac.compare_digest(password_hash, _hash_password(password, salt))


def _profile_name(email: str, player_name: str | None) -> str:
    return (player_name or "").strip() or email.split("@")[0]


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

    async def sign_in_verified(
        self, *, email: str, player_name: str | None, ttl: timedelta
    ) -> tuple[str, PlayerSessionStatus]:
        """Open a session for an email Supabase Auth has verified (spec 0027).

        Creates a free profile on first sign-in; an existing profile keeps its
        name and tier.
        """
        ...

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

    # Account settings (spec 0025). Emails are already trimmed and lower-cased.

    async def verify_password(self, email: str, password: str) -> bool:
        """Local (development) password check; ``False`` for Supabase-owned accounts."""
        ...

    async def set_password(self, email: str, password: str) -> None: ...

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
    # None when Supabase Auth owns the password (spec 0027).
    password_hash: str | None
    salt: str | None
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
        if account is None or not _password_matches(password, account.password_hash, account.salt):
            raise InvalidCredentialsError("Invalid email or password.")
        return self._open(account, ttl)

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
        waves, tests = self._usage.get((clean_email, _today_utc()), (0, 0))
        return token, _build_logged_in_status(
            email=clean_email,
            player_name=account.player_name,
            tier=account.tier,
            wave_runs_used=waves,
            test_runs_used=tests,
        )

    async def sign_in_verified(
        self, *, email: str, player_name: str | None, ttl: timedelta
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        account = self._accounts.get(clean_email)
        if account is None:
            account = _AccountRecord(
                email=clean_email,
                password_hash=None,
                salt=None,
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

    async def verify_password(self, email: str, password: str) -> bool:
        account = self._accounts.get(email)
        return account is not None and _password_matches(
            password, account.password_hash, account.salt
        )

    async def set_password(self, email: str, password: str) -> None:
        account = self._accounts[email]
        account.salt = secrets.token_hex(16)
        account.password_hash = _hash_password(password, account.salt)

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
            waves, tests = self._usage.pop((email, day))
            other_waves, other_tests = self._usage.get((new, day), (0, 0))
            self._usage[(new, day)] = (max(waves, other_waves), max(tests, other_tests))
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
                  password_hash text,
                  salt          text,
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
            self._relax_password_columns(connection)
            connection.execute(
                "delete from game.saved_boards where level_id in ('easy', 'medium', 'hard')"
            )
            # Mirrors the rename_agent_review_to_llm_review migration.
            connection.execute(
                "update game.saved_boards set save_json = "
                "replace(save_json, '\"agent_review\"', '\"llm_review\"') "
                "where save_json like '%\"agent_review\"%'"
            )

    @staticmethod
    def _relax_password_columns(connection: sqlite3.Connection) -> None:
        """Make the password columns nullable in databases created before spec 0027.

        SQLite cannot drop NOT NULL in place, so the table is rebuilt.
        """
        columns = connection.execute("pragma players.table_info(accounts)").fetchall()
        if not any(column[1] in ("password_hash", "salt") and column[3] for column in columns):
            return
        connection.executescript(
            """
            create table players.accounts_new (
              email         text primary key,
              password_hash text,
              salt          text,
              player_name   text not null,
              tier          text not null default 'free',
              created_at    text not null
            );
            insert into players.accounts_new
              select email, password_hash, salt, player_name, tier, created_at
              from players.accounts;
            drop table players.accounts;
            alter table players.accounts_new rename to accounts;
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
        # Usage left by a deleted account with this email still counts (API-ACCOUNT-009).
        return token, await self.lookup(token)

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
        if not _password_matches(password, account["password_hash"], account["salt"]):
            raise InvalidCredentialsError("Invalid email or password.")
        return await self._open(clean_email, ttl)

    async def _open(self, clean_email: str, ttl: timedelta) -> tuple[str, PlayerSessionStatus]:
        rows = await asyncio.to_thread(
            self._run,
            "select * from players.accounts where email = ?",
            (clean_email,),
        )
        account = rows[0]
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

    async def sign_in_verified(
        self, *, email: str, player_name: str | None, ttl: timedelta
    ) -> tuple[str, PlayerSessionStatus]:
        clean_email = email.strip().lower()
        await asyncio.to_thread(
            self._run,
            "insert into players.accounts"
            " (email, password_hash, salt, player_name, tier, created_at)"
            " values (?, null, null, ?, 'free', ?) on conflict(email) do nothing",
            (clean_email, _profile_name(clean_email, player_name), datetime.now(UTC).isoformat()),
        )
        return await self._open(clean_email, ttl)

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

    def _count(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        conn = self._connect()
        try:
            with conn:
                return conn.execute(sql, params).rowcount
        finally:
            conn.close()

    async def verify_password(self, email: str, password: str) -> bool:
        rows = await asyncio.to_thread(
            self._run,
            "select password_hash, salt from players.accounts where email = ?",
            (email,),
        )
        return bool(rows) and _password_matches(password, rows[0]["password_hash"], rows[0]["salt"])

    async def set_password(self, email: str, password: str) -> None:
        salt = secrets.token_hex(16)
        await asyncio.to_thread(
            self._run,
            "update players.accounts set password_hash = ?, salt = ? where email = ?",
            (_hash_password(password, salt), salt, email),
        )

    async def revoke_sessions(self, email: str, *, keep: str | None) -> None:
        await asyncio.to_thread(
            self._run,
            "delete from players.sessions where email = ? and token_hash <> ?",
            (email, _hash_token(keep) if keep else ""),
        )

    async def email_taken(self, email: str) -> bool:
        rows = await asyncio.to_thread(
            self._run, "select 1 from players.accounts where email = ?", (email,)
        )
        return bool(rows)

    async def move_email(self, old: str, new: str) -> None:
        def move() -> None:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "update game.saved_boards set email = ? where email = ?", (new, old)
                    )
                    conn.execute(
                        """
                        insert into players.daily_usage (email, usage_date, wave_runs, test_runs)
                          select ?, usage_date, wave_runs, test_runs
                          from players.daily_usage where email = ?
                        on conflict(email, usage_date) do update set
                          wave_runs = max(wave_runs, excluded.wave_runs),
                          test_runs = max(test_runs, excluded.test_runs)
                        """,
                        (new, old),
                    )
                    conn.execute("delete from players.daily_usage where email = ?", (old,))
                    conn.execute(
                        "update players.sessions set email = ? where email = ?", (new, old)
                    )
                    conn.execute(
                        "update players.accounts set email = ? where email = ?", (new, old)
                    )
            finally:
                conn.close()

        await asyncio.to_thread(move)

    async def delete_boards(self, email: str) -> int:
        return await asyncio.to_thread(
            self._count, "delete from game.saved_boards where email = ?", (email,)
        )

    async def delete_account(self, email: str) -> None:
        await asyncio.to_thread(self._run, "delete from players.sessions where email = ?", (email,))
        await asyncio.to_thread(self._run, "delete from players.accounts where email = ?", (email,))


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
            if account is None or not _password_matches(
                password, account["password_hash"], account["salt"]
            ):
                raise InvalidCredentialsError("Invalid email or password.")
            return self._open(account, ttl)

        token = await asyncio.to_thread(write)
        return token, await self.lookup(token)

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
                    "password_hash": None,
                    "salt": None,
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

    async def verify_password(self, email: str, password: str) -> bool:
        account = await asyncio.to_thread(self._account, email)
        return account is not None and _password_matches(
            password, account.get("password_hash"), account.get("salt")
        )

    async def set_password(self, email: str, password: str) -> None:
        salt = secrets.token_hex(16)
        await asyncio.to_thread(
            lambda: (
                self._table(self.ACCOUNTS_TABLE)
                .update({"password_hash": _hash_password(password, salt), "salt": salt})
                .eq("email", email)
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
                other = existing[0] if existing else {"wave_runs": 0, "test_runs": 0}
                self._table(self.USAGE_TABLE).upsert(
                    {
                        "email": new,
                        "usage_date": row["usage_date"],
                        "wave_runs": max(int(row["wave_runs"]), int(other["wave_runs"])),
                        "test_runs": max(int(row["test_runs"]), int(other["test_runs"])),
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
