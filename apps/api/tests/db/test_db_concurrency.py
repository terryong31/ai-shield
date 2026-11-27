"""Concurrent calls to the stored functions on real connections (spec 0056)."""

from __future__ import annotations

import threading
import uuid
from datetime import date, timedelta

import psycopg
import pytest

from .conftest import LocalStack, purge

pytestmark = pytest.mark.db

WORKERS = 16


def _together(stack: LocalStack, sql: str, params: tuple[object, ...]) -> list[tuple[object, ...]]:
    """Run one statement on WORKERS connections at the same moment."""
    barrier = threading.Barrier(WORKERS)
    results: list[tuple[object, ...]] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            with psycopg.connect(stack.db_url, autocommit=True) as conn:
                barrier.wait(timeout=30)
                row = conn.execute(sql, params).fetchone()
            with lock:
                results.append(tuple(row or ()))
        except BaseException as exc:
            with lock:
                failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert failures == []
    return results


@pytest.mark.spec("API-DB-006")
def test_concurrent_reservations_stop_exactly_at_the_limit(stack: LocalStack, email: str) -> None:
    try:
        results = _together(
            stack,
            "select reserved from players.reserve_daily_usage(%s, %s, 'wave', 5)",
            (email, date(2026, 11, 27)),
        )
        assert sorted(r[0] for r in results).count(True) == 5
        assert len(results) == WORKERS
        with psycopg.connect(stack.db_url) as conn:
            stored = conn.execute(
                "select wave_runs from players.daily_usage where email = %s", (email,)
            ).fetchone()
        assert stored == (5,)
    finally:
        purge(stack, email)


@pytest.mark.spec("API-DB-006")
def test_concurrent_fulfilment_grants_one_pass(stack: LocalStack, email: str) -> None:
    purchase_id = uuid.uuid4()
    try:
        with psycopg.connect(stack.db_url, autocommit=True) as conn:
            conn.execute(
                "insert into players.accounts (email, player_name, tier) values (%s, 'DB', 'free')",
                (email,),
            )
            conn.execute(
                "insert into players.purchases (id, email, amount_cents, currency, livemode, "
                "status) values (%s, %s, 500, 'usd', false, 'pending')",
                (purchase_id, email),
            )
        results = _together(
            stack,
            "select players.fulfil_purchase(%s, %s, 500, 'usd', 30)",
            (purchase_id, f"pi_{purchase_id.hex}"),
        )
        outcomes = sorted(str(r[0]) for r in results)
        assert outcomes.count("fulfilled") == 1
        assert outcomes.count("duplicate") == WORKERS - 1
        with psycopg.connect(stack.db_url) as conn:
            row = conn.execute(
                "select a.paid_until, p.starts_at from players.accounts a "
                "join players.purchases p on p.email = a.email where p.id = %s",
                (purchase_id,),
            ).fetchone()
        assert row is not None
        assert row[0] - row[1] == timedelta(days=30)
    finally:
        purge(stack, email)
