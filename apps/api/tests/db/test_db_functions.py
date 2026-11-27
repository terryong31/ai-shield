"""Constraints and stored functions on the real database (spec 0056)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import psycopg
import pytest
from psycopg import errors

pytestmark = pytest.mark.db

TODAY = date(2026, 11, 27)


def _account(db: psycopg.Connection, email: str, paid_until: datetime | None = None) -> None:
    db.execute(
        "insert into players.accounts (email, player_name, tier, paid_until) "
        "values (%s, 'DB test', 'free', %s)",
        (email, paid_until),
    )


def _purchase(
    db: psycopg.Connection,
    email: str | None,
    *,
    status: str = "pending",
    livemode: bool = False,
    payment_intent: str | None = None,
) -> uuid.UUID:
    purchase_id = uuid.uuid4()
    db.execute(
        "insert into players.purchases (id, email, amount_cents, currency, livemode, status, "
        "payment_intent) values (%s, %s, 500, 'usd', %s, %s, %s)",
        (purchase_id, email, livemode, status, payment_intent),
    )
    return purchase_id


def _paid_until(db: psycopg.Connection, email: str) -> datetime:
    row = db.execute(
        "select paid_until from players.accounts where email = %s", (email,)
    ).fetchone()
    assert row is not None
    value: datetime = row[0]
    return value


@pytest.mark.spec("API-DB-003")
def test_one_pending_purchase_per_email_and_mode(db: psycopg.Connection, email: str) -> None:
    _account(db, email)
    _purchase(db, email, livemode=False)
    _purchase(db, email, livemode=True)
    for status in ("expired", "expired", "paid", "paid"):
        _purchase(db, email, status=status)
    _purchase(db, email, status="expired", payment_intent=None)
    _purchase(db, email, status="expired", payment_intent=None)

    db.execute("savepoint dup")
    with pytest.raises(errors.UniqueViolation) as caught:
        _purchase(db, email, livemode=False)
    assert caught.value.sqlstate == "23505"
    db.execute("rollback to savepoint dup")


def _reserve(
    db: psycopg.Connection, email: str, kind: str, limit: int
) -> tuple[bool, int, int, int]:
    row = db.execute(
        "select * from players.reserve_daily_usage(%s, %s, %s, %s)", (email, TODAY, kind, limit)
    ).fetchone()
    assert row is not None
    return (bool(row[0]), int(row[1]), int(row[2]), int(row[3]))


def _release(db: psycopg.Connection, email: str, kind: str) -> tuple[int, int, int] | None:
    row = db.execute(
        "select * from players.release_daily_usage(%s, %s, %s)", (email, TODAY, kind)
    ).fetchone()
    return None if row is None else (int(row[0]), int(row[1]), int(row[2]))


@pytest.mark.spec("API-DB-004")
def test_daily_usage_counts_up_to_the_limit_and_never_below_zero(
    db: psycopg.Connection, email: str
) -> None:
    assert _reserve(db, email, "wave", 0) == (False, 0, 0, 0)
    assert _reserve(db, email, "wave", 2) == (True, 1, 0, 0)
    assert _reserve(db, email, "wave", 2) == (True, 2, 0, 0)
    assert _reserve(db, email, "wave", 2) == (False, 2, 0, 0)
    assert _reserve(db, email, "test", 1) == (True, 2, 1, 0)
    assert _reserve(db, email, "train", 3) == (True, 2, 1, 1)
    assert _reserve(db, email, "wave", -1) == (False, 2, 1, 1)

    db.execute("savepoint kind")
    with pytest.raises(errors.RaiseException):
        _reserve(db, email, "chat", 5)
    db.execute("rollback to savepoint kind")

    assert _release(db, email, "train") == (2, 1, 0)
    assert _release(db, email, "train") == (2, 1, 0)
    assert _release(db, email, "wave") == (1, 1, 0)


def _fulfil(
    db: psycopg.Connection, purchase_id: uuid.UUID | None, intent: str, *, amount: int = 500
) -> str:
    row = db.execute(
        "select players.fulfil_purchase(%s, %s, %s, 'usd', 30)", (purchase_id, intent, amount)
    ).fetchone()
    assert row is not None
    return str(row[0])


@pytest.mark.spec("API-DB-005")
def test_fulfil_revoke_and_restore_move_the_exact_intervals(
    db: psycopg.Connection, email: str
) -> None:
    assert _fulfil(db, uuid.uuid4(), "pi_unknown") == "unknown"
    assert _fulfil(db, _purchase(db, None, status="expired"), "pi_orphan") == "orphaned"
    no_account = f"dbtest+{uuid.uuid4().hex}@example.invalid"
    assert _fulfil(db, _purchase(db, no_account), "pi_none") == "no_account"

    _account(db, email)
    first = _purchase(db, email)
    assert _fulfil(db, first, "pi_mismatch", amount=499) == "mismatch"
    assert _fulfil(db, first, "pi_first") == "fulfilled"
    assert _fulfil(db, first, "pi_first") == "duplicate"
    start = db.execute(
        "select starts_at, ends_at from players.purchases where id = %s", (first,)
    ).fetchone()
    assert start is not None
    assert start[1] - start[0] == timedelta(days=30)
    assert _paid_until(db, email) == start[1]

    # A second pass stacks after the first.
    second = _purchase(db, email, status="expired")
    assert _fulfil(db, second, "pi_second") == "fulfilled"
    stacked = db.execute(
        "select starts_at, ends_at from players.purchases where id = %s", (second,)
    ).fetchone()
    assert stacked is not None
    assert stacked[0] == start[1]
    assert _paid_until(db, email) == start[1] + timedelta(days=30)

    # Refunding the first pass removes its unused days and moves the second one forward.
    before = _paid_until(db, email)
    revoked = db.execute(
        "select players.revoke_purchase(%s, null, 'refunded')", (first,)
    ).fetchone()
    assert revoked == ("revoked",)
    removed = db.execute("select removed from players.purchases where id = %s", (first,)).fetchone()
    assert removed is not None
    assert timedelta(days=29, hours=23) < removed[0] <= timedelta(days=30)
    assert _paid_until(db, email) == before - removed[0]
    moved = db.execute(
        "select starts_at, ends_at from players.purchases where id = %s", (second,)
    ).fetchone()
    assert moved is not None
    assert moved[0] == stacked[0] - removed[0]
    assert moved[1] - moved[0] == timedelta(days=30)
    duplicate = db.execute("select players.revoke_purchase(%s, null, 'refunded')", (first,))
    assert duplicate.fetchone() == ("duplicate",)

    # A failed refund gives the removed days back, after the current end.
    restored = db.execute("select players.restore_purchase('pi_first', 'refunded')").fetchone()
    assert restored == ("restored",)
    assert _paid_until(db, email) == before - removed[0] + removed[0]
    after = db.execute(
        "select status, removed, ends_at - starts_at from players.purchases where id = %s", (first,)
    ).fetchone()
    assert after == ("paid", timedelta(0), removed[0])

    # A dispute that the player wins restores the same way.
    assert db.execute(
        "select players.revoke_purchase(null, 'pi_second', 'disputed')"
    ).fetchone() == ("revoked",)
    assert db.execute("select players.restore_purchase('pi_second', 'disputed')").fetchone() == (
        "restored",
    )
    assert db.execute("select players.restore_purchase('pi_missing', 'disputed')").fetchone() == (
        "unknown",
    )
