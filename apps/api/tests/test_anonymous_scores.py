"""Server-side anonymous scores and their promotion on sign-in (spec 0052)."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from shield_api.schemas import ScoreCreateRequest
from shield_api.services.anonymous_scores import (
    InMemoryAnonymousScoreStore,
    SupabaseAnonymousScoreStore,
)
from shield_api.services.players import SupabasePlayerStore

from .conftest import FakeClient, Harness
from .test_game_api import _valid_board_payload

COOKIE = "shield_player_session"
PASSWORD = "Str0ngPassw0rd"
EMAIL = "ada@example.com"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _score(
    total: int, *, level: str = "easy-1", won: bool = True, latency: float = 1.0
) -> ScoreCreateRequest:
    return ScoreCreateRequest.model_validate(
        {
            "player_name": "Ada",
            "level_id": level,
            "total_score": total,
            "medal": "gold",
            "attacks_blocked": 12,
            "attacks_total": 12,
            "false_alarms": 0,
            "avg_latency_ms": latency,
            "total_cost_usd": 0.0,
            "board": _valid_board_payload(),
            "won": won,
            "mastered": False,
        }
    )


def _anonymous_win(harness: Harness) -> str:
    anon = harness.client.post("/api/v1/auth/anonymous")
    assert anon.status_code == 200
    token = harness.client.cookies[COOKIE]
    run = harness.client.post(
        "/api/v1/game/run", json={"level_id": "easy-1", "board": _valid_board_payload()}
    )
    assert run.status_code == 200
    assert run.json()["score"]["won"] is True
    return token


def _leaderboard_names(harness: Harness) -> list[str]:
    rows = harness.client.get("/api/v1/game/scores", params={"level_id": "easy-1"}).json()
    return [row["player_name"] for row in rows]


@pytest.mark.spec("API-ANONSCORE-001")
def test_anonymous_win_is_kept_server_side_and_not_on_the_leaderboard(harness: Harness) -> None:
    token = _anonymous_win(harness)

    pending = asyncio.run(harness.container.anonymous_scores.list_for(_hash(token)))
    assert [row.level_id for row in pending] == ["easy-1"]
    assert pending[0].won is True
    assert asyncio.run(harness.scores.list_scores(level_id="easy-1")) == []
    assert _leaderboard_names(harness) == []

    progress = harness.client.get("/api/v1/game/progress").json()
    easy_1 = next(item for item in progress["levels"] if item["level_id"] == "easy-1")
    assert easy_1["won"] is True
    assert easy_1["best_score"] == pending[0].total_score


@pytest.mark.spec("API-ANONSCORE-001")
def test_anonymous_store_keeps_the_better_run_and_sticky_flags() -> None:
    store = InMemoryAnonymousScoreStore()
    asyncio.run(store.record("h", _score(9000), ttl=timedelta(days=7)))
    asyncio.run(store.record("h", _score(4000, won=False), ttl=timedelta(days=7)))
    rows = asyncio.run(store.list_for("h"))
    assert [(r.total_score, r.won) for r in rows] == [(9000, True)]


@pytest.mark.spec("API-ANONSCORE-002")
def test_sign_in_promotes_anonymous_scores_and_rotates_the_session(harness: Harness) -> None:
    harness.auth.add(EMAIL, PASSWORD)
    token = _anonymous_win(harness)

    login = harness.client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200

    new_token = harness.client.cookies[COOKIE]
    assert new_token != token
    assert asyncio.run(harness.container.players.lookup(token)).authenticated is False
    assert asyncio.run(harness.container.anonymous_scores.list_for(_hash(token))) == []
    owned = asyncio.run(harness.scores.list_scores_for_owner(EMAIL))
    assert [row.level_id for row in owned] == ["easy-1"]
    assert owned[0].won is True
    assert len(_leaderboard_names(harness)) == 1


@pytest.mark.spec("API-ANONSCORE-003")
def test_promotion_keeps_the_higher_of_the_account_and_anonymous_scores(
    harness: Harness,
) -> None:
    harness.auth.add(EMAIL, PASSWORD)
    # The same top score, but faster: the account's run ranks higher.
    asyncio.run(harness.scores.record_score(_score(10000, latency=0.0), email=EMAIL))
    token = _anonymous_win(harness)
    anonymous = asyncio.run(harness.container.anonymous_scores.list_for(_hash(token)))[0]
    assert anonymous.avg_latency_ms > 0.0

    harness.client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    owned = asyncio.run(harness.scores.list_scores_for_owner(EMAIL))
    assert [(row.total_score, row.avg_latency_ms) for row in owned] == [(10000, 0.0)]


@pytest.mark.spec("API-ANONSCORE-003")
def test_promotion_raises_a_lower_account_score(harness: Harness) -> None:
    harness.auth.add(EMAIL, PASSWORD)
    asyncio.run(harness.scores.record_score(_score(100, won=False), email=EMAIL))
    token = _anonymous_win(harness)
    anon_total = asyncio.run(harness.container.anonymous_scores.list_for(_hash(token)))[0]

    harness.client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    owned = asyncio.run(harness.scores.list_scores_for_owner(EMAIL))
    assert [row.total_score for row in owned] == [anon_total.total_score]


@pytest.mark.spec("API-ANONSCORE-004")
def test_no_promotion_from_an_expired_or_signed_in_cookie(harness: Harness) -> None:
    harness.auth.add(EMAIL, PASSWORD)
    harness.auth.add("grace@example.com", PASSWORD)
    stale = "expired-anonymous-token"
    asyncio.run(
        harness.container.anonymous_scores.record(_hash(stale), _score(9000), ttl=timedelta(days=7))
    )
    harness.client.cookies.clear()
    harness.client.cookies.set(COOKIE, stale)
    login = harness.client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert asyncio.run(harness.scores.list_scores_for_owner(EMAIL)) == []

    ada_token = login.cookies[COOKIE]
    harness.client.cookies.clear()
    harness.client.cookies.set(COOKIE, ada_token)
    asyncio.run(
        harness.container.anonymous_scores.record(
            _hash(ada_token), _score(9500), ttl=timedelta(days=7)
        )
    )
    harness.client.post(
        "/api/v1/auth/login", json={"email": "grace@example.com", "password": PASSWORD}
    )
    assert asyncio.run(harness.scores.list_scores_for_owner("grace@example.com")) == []


@pytest.mark.spec("API-ANONSCORE-005")
def test_saves_reject_client_score_fields(harness: Harness) -> None:
    harness.auth.add(EMAIL, PASSWORD)
    harness.client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    payload: dict[str, Any] = {
        "board": _valid_board_payload(),
        "positions": {},
        "score": 10000,
        "medal": "gold",
        "won": True,
        "mastered": True,
    }
    response = harness.client.put("/api/v1/game/saves/easy-1", json=payload)
    assert response.status_code == 422
    assert asyncio.run(harness.scores.list_scores_for_owner(EMAIL)) == []


@pytest.mark.spec("API-ANONSCORE-001")
def test_supabase_anonymous_store_round_trip() -> None:
    client = FakeClient()
    store = SupabaseAnonymousScoreStore(client)
    asyncio.run(store.record("h", _score(7000), ttl=timedelta(days=7)))
    asyncio.run(store.record("h", _score(8000), ttl=timedelta(days=7)))
    asyncio.run(store.record("h", _score(6000), ttl=timedelta(days=7)))
    rows = asyncio.run(store.list_for("h"))
    assert [r.total_score for r in rows] == [8000]
    asyncio.run(store.delete_for("h"))
    assert asyncio.run(store.list_for("h")) == []


@pytest.mark.spec("API-DRAFT-001")
def test_session_insert_prunes_only_stale_anonymous_rows() -> None:
    client = FakeClient()
    now = datetime.now(UTC)
    today = now.date()
    old_day = (today - timedelta(days=8)).isoformat()
    recent_day = (today - timedelta(days=2)).isoformat()
    usage = client.schema("players").table("daily_usage")
    usage.rows = [
        {"email": "anon:old", "usage_date": old_day, "wave_runs": 1},
        {"email": "anon:recent", "usage_date": recent_day, "wave_runs": 1},
        {"email": EMAIL, "usage_date": old_day, "wave_runs": 1},
    ]
    anon_scores = client.schema("game").table("anonymous_scores")
    anon_scores.rows = [
        {"session_token_hash": "gone", "expires_at": (now - timedelta(minutes=1)).isoformat()},
        {"session_token_hash": "live", "expires_at": (now + timedelta(days=1)).isoformat()},
    ]

    store = SupabasePlayerStore(client)
    asyncio.run(store.create_anonymous(timedelta(minutes=30)))

    assert sorted(r["email"] for r in usage.rows) == sorted(["anon:recent", EMAIL])
    assert [r["session_token_hash"] for r in anon_scores.rows] == ["live"]


@pytest.mark.spec("API-DRAFT-001")
def test_cleanup_failure_never_blocks_a_session_and_runs_at_most_every_few_minutes() -> None:
    client = FakeClient()
    client.schema("game").table("anonymous_scores").fail = True
    store = SupabasePlayerStore(client)

    token, status = asyncio.run(store.create_anonymous(timedelta(minutes=30)))
    assert status.is_anonymous is True
    assert asyncio.run(store.lookup(token)).authenticated is True

    client.accessed.clear()
    asyncio.run(store.create_anonymous(timedelta(minutes=30)))
    assert ("game", "anonymous_scores") not in client.accessed
