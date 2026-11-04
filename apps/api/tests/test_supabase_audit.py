"""SupabaseAuditLog against an in-process fake of the supabase-py query builder."""

import pytest

from shield_api.services.audit import SupabaseAuditLog


async def record(log: SupabaseAuditLog, query: str, action: str) -> None:
    await log.record(query=query, action=action, reason="r", layer="SYSTEM", metadata={})


async def test_records_round_trip_newest_first(fake_supabase) -> None:
    log = SupabaseAuditLog(fake_supabase())
    await record(log, "first", "ALLOWED")
    await record(log, "second", "BLOCKED")

    recent = await log.recent(10)

    assert [r.query for r in recent] == ["second", "first"]
    assert recent[0].reviewed is False


async def test_stats_use_server_side_counts(fake_supabase) -> None:
    log = SupabaseAuditLog(fake_supabase())
    for action in ("ALLOWED", "BLOCKED", "BLOCKED"):
        await record(log, "q", action)

    stats = await log.stats()

    assert (stats.total, stats.blocked, stats.allowed, stats.block_rate) == (3, 2, 1, 66.7)


async def test_review_updates_label_and_action(fake_supabase) -> None:
    client = fake_supabase()
    log = SupabaseAuditLog(client)
    await record(log, "q", "BLOCKED")

    await log.review("0", 0)

    assert (client.requests.rows[0]["action"], client.requests.rows[0]["human_label"]) == (
        "ALLOWED",
        0,
    )


async def test_write_failures_are_logged_not_raised(
    fake_supabase, caplog: pytest.LogCaptureFixture
) -> None:
    log = SupabaseAuditLog(fake_supabase(fail=True))

    await record(log, "q", "ALLOWED")
    await log.review("0", 1)

    assert "failed to write audit record" in caplog.text
    assert "failed to update audit review" in caplog.text
