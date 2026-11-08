"""One behavioural contract, run against every AuditLog backend (spec 0009)."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from shield_api.services.audit import (
    AuditLog,
    InMemoryAuditLog,
    SqliteAuditLog,
    SupabaseAuditLog,
)
from shield_api.services.sqlite import connect_domains

MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


@pytest.fixture(params=["memory", "sqlite", "supabase"])
def audit_log(request, tmp_path: Path, fake_supabase: Callable) -> AuditLog:
    match request.param:
        case "memory":
            return InMemoryAuditLog()
        case "sqlite":
            return SqliteAuditLog(tmp_path / "audit.db")
        case _:
            return SupabaseAuditLog(fake_supabase())


async def add(log: AuditLog, query: str, action: str = "ALLOWED") -> None:
    await log.record(
        query=query, action=action, reason="r", layer="SYSTEM", metadata={"mlConfidence": 0.1}
    )


@pytest.mark.spec("API-STORE-003")
async def test_recent_is_newest_first_and_limited(audit_log: AuditLog) -> None:
    for query in ("one", "two", "three"):
        await add(audit_log, query)

    recent = await audit_log.recent(2)

    assert [r.query for r in recent] == ["three", "two"]
    assert recent[0].metadata == {"mlConfidence": 0.1}
    assert recent[0].reviewed is False
    assert recent[0].human_label is None


@pytest.mark.spec("API-STORE-003")
async def test_stats_follow_the_shared_definition(audit_log: AuditLog) -> None:
    assert (await audit_log.stats()).block_rate == 0.0
    for action in ("ALLOWED", "BLOCKED", "BLOCKED"):
        await add(audit_log, "q", action)

    stats = await audit_log.stats()

    assert (stats.total, stats.blocked, stats.allowed, stats.block_rate) == (3, 2, 1, 66.7)


@pytest.mark.spec("API-STORE-003")
async def test_review_sets_label_and_action_and_ignores_unknown_ids(audit_log: AuditLog) -> None:
    await add(audit_log, "q", "BLOCKED")
    record_id = (await audit_log.recent(1))[0].id

    await audit_log.review(record_id, 0)
    await audit_log.review("00000000-0000-0000-0000-000000000000", 1)

    (record,) = await audit_log.recent(10)
    assert (record.reviewed, record.human_label, record.action) == (True, 0, "ALLOWED")


@pytest.mark.spec("API-STORE-002")
async def test_sqlite_records_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "shield.db"
    await add(SqliteAuditLog(path), "before restart")

    reopened = SqliteAuditLog(path)

    assert [r.query for r in await reopened.recent(10)] == ["before restart"]


def _migration_columns() -> set[str]:
    sql = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql")))
    body = re.search(r"create table public\.requests \((.*?)\n\);", sql, re.S | re.I)
    assert body, "no create table public.requests in supabase/migrations"
    return {line.split()[0] for line in body.group(1).strip().splitlines() if line.strip()}


@pytest.mark.spec("API-STORE-006")
def test_sqlite_schema_mirrors_the_supabase_migration(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    SqliteAuditLog(path)

    # Spec 0024 moved the table into the attached `audit` schema (audit.requests).
    connection = connect_domains(path)
    try:
        columns = {row[1] for row in connection.execute("pragma audit.table_info(requests)")}
    finally:
        connection.close()

    assert columns == _migration_columns()
