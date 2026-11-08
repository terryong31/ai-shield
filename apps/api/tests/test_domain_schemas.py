"""Domain-scoped storage: `audit`, `game` and `players` schemas (spec 0024)."""

from __future__ import annotations

import re
import sqlite3
import tomllib
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from shield_api.container import build_container
from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
from shield_api.services.audit import SqliteAuditLog, SupabaseAuditLog
from shield_api.services.players import (
    InMemoryPlayerStore,
    InvalidCredentialsError,
    PlayerAlreadyExistsError,
    PlayerStore,
    SqlitePlayerStore,
    SupabasePlayerStore,
)
from shield_api.services.sessions import (
    InMemorySessionStore,
    SessionStore,
    SqliteSessionStore,
    SupabaseSessionStore,
)
from shield_api.services.sqlite import connect_domains
from shield_api.settings import Settings

from .conftest import FakeClient

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "supabase" / "migrations"

DOMAIN_TABLES: dict[str, tuple[str, ...]] = {
    "audit": ("requests", "clearance_sessions"),
    "game": ("scores", "saved_boards"),
    "players": ("accounts", "sessions", "daily_usage"),
}
TTL = timedelta(hours=1)


def _migration_sql() -> str:
    return "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql"))).lower()


def _migration_columns(schema: str, table: str) -> set[str]:
    sql = _migration_sql()
    body = re.search(rf"create table (?:if not exists )?{schema}\.{table} \((.*?)\n\);", sql, re.S)
    if body is None and schema == "audit" and table == "requests":
        # audit.requests is public.requests moved into the audit schema.
        body = re.search(r"create table public\.requests \((.*?)\n\);", sql, re.S)
    assert body, f"no create table {schema}.{table} in supabase/migrations"
    columns = set()
    for line in body.group(1).strip().splitlines():
        word = line.strip().split()[0] if line.strip() else ""
        if word and word not in {"primary", "constraint", "unique", "check", "foreign"}:
            columns.add(word.strip(","))
    return columns


def _score(name: str, total: int) -> ScoreCreateRequest:
    return ScoreCreateRequest(
        player_name=name,
        level_id="medium",
        total_score=total,
        medal="bronze",
        attacks_blocked=2,
        attacks_total=4,
        false_alarms=0,
        avg_latency_ms=10.0,
        total_cost_usd=0.001,
        board=BoardGraphSchema(nodes=[], edges=[]),
    )


@pytest.mark.spec("API-SCHEMA-001")
def test_migrations_put_every_table_in_a_locked_down_domain_schema() -> None:
    sql = _migration_sql()

    for schema in DOMAIN_TABLES:
        assert f"create schema if not exists {schema}" in sql
        assert re.search(rf"revoke all on schema {schema} from [^;]*anon", sql)
        assert re.search(rf"revoke all on schema {schema} from [^;]*authenticated", sql)
        assert f"grant usage on schema {schema} to service_role" in sql
        assert re.search(rf"grant all on all tables in schema {schema} to service_role", sql)

    assert "alter table if exists public.requests set schema audit" in sql
    for created in re.findall(r"create table (?:if not exists )?public\.(\w+)", sql):
        assert f"alter table if exists public.{created} set schema" in sql

    for schema, tables in DOMAIN_TABLES.items():
        for table in tables:
            assert f"alter table {schema}.{table} enable row level security" in sql
            assert re.search(
                rf"revoke all on table {schema}\.{table} from [^;]*anon[^;]*authenticated", sql
            ), f"{schema}.{table} privileges are not revoked"
            assert _migration_columns(schema, table)


@pytest.mark.spec("API-SCHEMA-002")
def test_postgrest_exposes_only_the_domain_schemas_and_seed_targets_audit() -> None:
    config = tomllib.loads((ROOT / "supabase" / "config.toml").read_text())
    schemas = config["api"]["schemas"]
    assert {"audit", "game", "players"} <= set(schemas)
    assert "public" not in schemas

    seed = (ROOT / "supabase" / "seed.sql").read_text().lower()
    assert "insert into audit.requests" in seed
    assert "public.requests" not in seed


@pytest.mark.spec("API-SCHEMA-003")
async def test_supabase_audit_log_uses_audit_requests_and_persists_game_scores(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    client = fake_supabase()
    log = SupabaseAuditLog(client)

    await log.record(query="q", action="BLOCKED", reason="r", layer="SYSTEM", metadata={})
    assert [r.query for r in await log.recent(5)] == ["q"]
    assert (await log.stats()).blocked == 1
    record_id = (await log.recent(1))[0].id
    await log.review(record_id, 0)
    assert client.tables[("audit", "requests")].rows[0]["human_label"] == 0

    await log.record_score(_score("ada", 6000))
    await log.record_score(_score("ada", 5000))  # lower: keeps the best
    await log.record_score(_score("grace", 7000))
    assert len(client.tables[("game", "scores")].rows) == 2

    reopened = SupabaseAuditLog(client)
    listed = await reopened.list_scores(level_id="medium")
    assert [(s.player_name, s.total_score) for s in listed] == [("grace", 7000), ("ada", 6000)]
    assert {s.score_version for s in listed} == {2}

    await reopened.clear_scores()
    assert await reopened.list_scores() == []
    assert {schema for schema, _ in client.accessed} <= {"audit", "game"}
    assert ("game", "scores") in client.accessed


def _session_stores(tmp_path: Path, client: FakeClient) -> list[SessionStore]:
    return [
        InMemorySessionStore(),
        SqliteSessionStore(tmp_path / "s.db"),
        SupabaseSessionStore(client),
    ]


def _player_stores(tmp_path: Path, client: FakeClient) -> list[PlayerStore]:
    return [
        InMemoryPlayerStore(),
        SqlitePlayerStore(tmp_path / "p.db"),
        SupabasePlayerStore(client),
    ]


@pytest.mark.spec("API-SCHEMA-004")
async def test_supabase_session_and_player_stores_honour_the_store_contracts(
    tmp_path: Path, fake_supabase: Callable[..., FakeClient]
) -> None:
    client = fake_supabase()

    for sessions in _session_stores(tmp_path, client):
        token, expires_at = await sessions.create(TTL)
        assert await sessions.lookup(token) == expires_at
        stale, _ = await sessions.create(timedelta(seconds=-1))
        assert await sessions.lookup(stale) is None
        await sessions.revoke(token)
        assert await sessions.lookup(token) is None
    assert ("audit", "clearance_sessions") in client.accessed
    stored = client.tables[("audit", "clearance_sessions")].rows
    assert all(len(row["token_hash"]) == 64 for row in stored)

    for players in _player_stores(tmp_path, client):
        anon_token, anon = await players.create_anonymous(TTL)
        assert anon.is_anonymous
        assert (await players.consume_run(anon_token, is_custom_test=False)).wave_runs_used == 1

        token, status = await players.register(
            email="Ada@Example.com", password="password123", player_name="Ada", ttl=TTL
        )
        assert (status.tier, status.email) == ("free", "ada@example.com")
        with pytest.raises(PlayerAlreadyExistsError):
            await players.register(
                email="ada@example.com", password="x" * 8, player_name=None, ttl=TTL
            )
        with pytest.raises(InvalidCredentialsError):
            await players.login(email="ada@example.com", password="wrong-pass", ttl=TTL)

        await players.consume_run(token, is_custom_test=False)
        await players.consume_run(token, is_custom_test=True)
        looked = await players.lookup(token)
        assert (looked.wave_runs_used, looked.test_runs_used) == (1, 1)

        upgraded = await players.upgrade(token)
        assert upgraded.tier == "paid"
        relogged, again = await players.login(
            email="ada@example.com", password="password123", ttl=TTL
        )
        assert (again.tier, again.wave_runs_used) == ("paid", 1)

        await players.revoke(relogged)
        assert (await players.lookup(relogged)).authenticated is False

    touched = {table for schema, table in client.accessed if schema == "players"}
    assert touched == {"accounts", "sessions", "daily_usage"}
    accounts = client.tables[("players", "accounts")].rows
    assert all("password123" not in str(row) for row in accounts)


@pytest.mark.spec("API-SCHEMA-005")
def test_supabase_settings_wire_every_store_and_otherwise_fall_back_to_sqlite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[FakeClient] = []

    def fake_create(url: str, key: str) -> FakeClient:
        client = FakeClient()
        created.append(client)
        return client

    monkeypatch.setattr("supabase.create_client", fake_create)
    base = {
        "_env_file": None,
        "FEEDBACK_PATH": tmp_path / "f.csv",
        "SQLITE_PATH": tmp_path / "var" / "shield.db",
    }

    online = build_container(
        Settings(**base, SUPABASE_URL="https://x.supabase.co", SUPABASE_KEY=SecretStr("k"))
    )
    assert isinstance(online.audit_log, SupabaseAuditLog)
    assert isinstance(online.sessions, SupabaseSessionStore)
    assert isinstance(online.players, SupabasePlayerStore)
    assert len(created) == 1

    for partial in ({"SUPABASE_URL": "https://x.supabase.co"}, {"SUPABASE_KEY": SecretStr("k")}):
        offline = build_container(Settings(**base, **partial))
        assert isinstance(offline.audit_log, SqliteAuditLog)
        assert isinstance(offline.sessions, SqliteSessionStore)
        assert isinstance(offline.players, SqlitePlayerStore)


@pytest.mark.spec("API-SCHEMA-006")
def test_sqlite_stores_use_attached_domain_schemas_that_mirror_the_migrations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shield.db"
    SqliteAuditLog(path)
    SqliteSessionStore(path)
    SqlitePlayerStore(path)

    connection = connect_domains(path)
    try:
        main_tables = connection.execute(
            "select name from main.sqlite_master where type = 'table'"
        ).fetchall()
        assert main_tables == []
        for schema, tables in DOMAIN_TABLES.items():
            found = {
                row[0]
                for row in connection.execute(
                    f"select name from {schema}.sqlite_master where type = 'table'"  # noqa: S608
                )
            }
            assert found == set(tables), schema
            for table in tables:
                columns = {
                    row[1] for row in connection.execute(f"pragma {schema}.table_info({table})")
                }
                assert columns == _migration_columns(schema, table), f"{schema}.{table}"
    finally:
        connection.close()

    with sqlite3.connect(path) as plain:
        assert plain.execute("select count(*) from sqlite_master").fetchone() == (0,)
