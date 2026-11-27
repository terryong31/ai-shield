"""The Supabase stores against the real local PostgREST (spec 0056)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import psycopg
import pytest

from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
from shield_api.services.players import PurchasePendingError, SupabasePlayerStore
from shield_api.services.scores import SupabaseScoreStore
from shield_api.services.sessions import SupabaseSessionStore

from .conftest import LocalStack, purge

pytestmark = pytest.mark.db

BOARD = BoardGraphSchema(nodes=[], edges=[])


def _client(stack: LocalStack) -> Any:
    from supabase import create_client

    return create_client(stack.api_url, stack.service_key)


def _score(name: str, total: int, *, won: bool) -> ScoreCreateRequest:
    return ScoreCreateRequest(
        player_name=name,
        level_id="easy-1",
        total_score=total,
        medal="gold",
        attacks_blocked=12,
        attacks_total=12,
        false_alarms=0,
        avg_latency_ms=1.0,
        total_cost_usd=0.0,
        board=BOARD,
        won=won,
        mastered=False,
    )


@pytest.mark.spec("API-DB-007")
def test_score_store_keeps_the_best_run_and_hides_the_email(stack: LocalStack, email: str) -> None:
    store = SupabaseScoreStore(_client(stack))
    name = f"DB {uuid.uuid4().hex[:8]}"
    try:
        asyncio.run(store.record_score_change(_score(name, 9000, won=True), email=email))
        lower = asyncio.run(store.record_score_change(_score(name, 3000, won=False), email=email))
        assert lower.changed is False
        owned = asyncio.run(store.list_scores_for_owner(email))
        assert [(r.total_score, r.won) for r in owned] == [(9000, True)]
        listed = asyncio.run(store.list_scores(level_id="easy-1", limit=100))
        mine = [r for r in listed if r.player_name == name]
        assert len(mine) == 1
        assert email not in mine[0].model_dump_json()
    finally:
        purge(stack, email)


@pytest.mark.spec("API-DB-007")
def test_player_store_round_trips_saves_purchases_moves_and_deletes(
    stack: LocalStack, email: str
) -> None:
    store = SupabasePlayerStore(_client(stack))
    moved = f"dbtest+{uuid.uuid4().hex}@example.invalid"
    try:
        token, status = asyncio.run(
            store.sign_in_verified(email=email, player_name="DB tester", ttl=timedelta(minutes=5))
        )
        assert status.email == email
        assert asyncio.run(store.lookup(token)).authenticated is True

        asyncio.run(store.save_board(email, "easy-1", {"board": {"nodes": [], "edges": []}}))
        loaded = asyncio.run(store.load_board(email, "easy-1"))
        assert loaded is not None
        assert loaded[0] == {"board": {"nodes": [], "edges": []}}

        asyncio.run(store.create_purchase(email, amount_cents=500, currency="usd", livemode=False))
        with pytest.raises(PurchasePendingError):
            asyncio.run(
                store.create_purchase(email, amount_cents=500, currency="usd", livemode=False)
            )

        asyncio.run(store.move_email(email, moved))
        assert asyncio.run(store.load_board(moved, "easy-1")) is not None
        assert asyncio.run(store.load_board(email, "easy-1")) is None

        asyncio.run(store.delete_account(moved))
        with psycopg.connect(stack.db_url) as conn:
            account = conn.execute(
                "select 1 from players.accounts where email = %s", (moved,)
            ).fetchone()
            orphans = conn.execute(
                "select count(*) from players.purchases where email is null and created_at > "
                "now() - interval '5 minutes'"
            ).fetchone()
            owned = conn.execute(
                "select count(*) from players.purchases where email = %s", (moved,)
            ).fetchone()
        assert account is None
        assert owned == (0,)
        assert orphans is not None
        assert orphans[0] >= 1
    finally:
        purge(stack, email, moved)


@pytest.mark.spec("API-DB-007")
def test_session_store_creates_finds_and_revokes(stack: LocalStack) -> None:
    store = SupabaseSessionStore(_client(stack))
    token, expires_at = asyncio.run(store.create(timedelta(minutes=5)))
    try:
        assert asyncio.run(store.lookup(token)) == expires_at
    finally:
        asyncio.run(store.revoke(token))
    assert asyncio.run(store.lookup(token)) is None
