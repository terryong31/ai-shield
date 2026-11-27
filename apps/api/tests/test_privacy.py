"""Player data export, erasure and no emails in public scores (spec 0058)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from shield_api.schemas import ScoreCreateRequest
from shield_api.services.players import SupabasePlayerStore
from shield_api.settings import Settings

from .conftest import FakeClient, Harness
from .test_game_api import _valid_board_payload

PASSWORD = "Str0ngPassw0rd"
EXPORT = "/api/v1/auth/account/export"
SECRET = "p" * 40


def _sign_in(harness: Harness, email: str) -> str:
    harness.auth.add(email, PASSWORD)
    res = harness.client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200
    return res.cookies["shield_player_session"]


def _score(name: str, total: int) -> ScoreCreateRequest:
    return ScoreCreateRequest.model_validate(
        {
            "player_name": name,
            "level_id": "easy-1",
            "total_score": total,
            "medal": "gold",
            "attacks_blocked": 12,
            "attacks_total": 12,
            "false_alarms": 0,
            "avg_latency_ms": 1.0,
            "total_cost_usd": 0.0,
            "board": _valid_board_payload(),
            "won": True,
            "mastered": False,
        }
    )


@pytest.mark.spec("API-PRIV-001")
def test_export_needs_a_signed_in_player(harness: Harness) -> None:
    assert harness.client.get(EXPORT).status_code == 403
    harness.client.post("/api/v1/auth/anonymous")
    assert harness.client.get(EXPORT).status_code == 403


@pytest.mark.spec("API-PRIV-001")
def test_export_returns_only_the_players_own_data(harness: Harness) -> None:
    other = "grace@example.com"
    asyncio.run(harness.scores.record_score(_score("Grace", 9000), email=other))
    asyncio.run(harness.container.players.save_board(other, "easy-2", {"board": "grace"}))

    token = _sign_in(harness, "ada@example.com")
    asyncio.run(harness.scores.record_score(_score("Ada", 8000), email="ada@example.com"))
    asyncio.run(harness.container.players.save_board("ada@example.com", "easy-1", {"board": "ada"}))
    asyncio.run(
        harness.container.players.create_purchase(
            "ada@example.com", amount_cents=500, currency="usd", livemode=False
        )
    )

    res = harness.client.get(EXPORT)
    assert res.status_code == 200
    assert res.headers["cache-control"] == "private, no-store"
    body = res.json()
    assert set(body) == {"exported_at", "account", "saved_boards", "scores", "purchases"}
    assert body["account"]["email"] == "ada@example.com"
    assert [b["level_id"] for b in body["saved_boards"]] == ["easy-1"]
    assert body["saved_boards"][0]["save"] == {"board": "ada"}
    assert [s["total_score"] for s in body["scores"]] == [8000]
    assert [p["amount_cents"] for p in body["purchases"]] == [500]
    text = json.dumps(body)
    for leaked in ("grace", "token_hash", "password", token):
        assert leaked not in text.lower(), leaked


@pytest.mark.spec("API-PRIV-002")
def test_export_is_rate_limited_in_production(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com")
    harness.container.settings = Settings(
        _env_file=None,
        APP_ENV="production",
        SESSION_COOKIE_SECURE=False,
        TRUSTED_PROXY_SECRET=SECRET,
    )
    headers = {"x-shield-proxy-secret": SECRET, "sec-fetch-site": "same-origin"}
    statuses = [harness.client.get(EXPORT, headers=headers) for _ in range(6)]
    assert [r.status_code for r in statuses] == [200] * 5 + [429]
    assert int(statuses[-1].headers["Retry-After"]) > 0


@pytest.mark.spec("API-PRIV-003")
def test_account_deletion_prunes_old_usage_rows() -> None:
    client = FakeClient()
    email = "ada@example.com"
    today = datetime.now(UTC).date()
    usage = client.schema("players").table("daily_usage")
    usage.rows = [
        {"email": email, "usage_date": today.isoformat(), "wave_runs": 1},
        {"email": email, "usage_date": (today - timedelta(days=31)).isoformat(), "wave_runs": 1},
        {"email": "grace@example.com", "usage_date": (today - timedelta(days=40)).isoformat()},
    ]
    purchases = client.schema("players").table("purchases")
    purchases.rows = [{"id": "p1", "email": email, "status": "paid"}]
    client.schema("players").table("accounts").rows = [{"email": email, "player_name": "Ada"}]

    asyncio.run(SupabasePlayerStore(client).delete_account(email))

    left = [(r["email"], r["usage_date"]) for r in usage.rows]
    assert (email, today.isoformat()) in left
    assert all(not (e == email and d < (today - timedelta(days=30)).isoformat()) for e, d in left)
    assert ("grace@example.com", (today - timedelta(days=40)).isoformat()) in left
    assert purchases.rows[0]["email"] is None
    assert client.schema("players").table("accounts").rows == []


@pytest.mark.spec("API-PRIV-003")
def test_delete_account_removes_boards_scores_sessions_and_the_auth_user(harness: Harness) -> None:
    token = _sign_in(harness, "ada@example.com")
    asyncio.run(harness.scores.record_score(_score("Ada", 8000), email="ada@example.com"))
    asyncio.run(harness.container.players.save_board("ada@example.com", "easy-1", {"board": "ada"}))
    res = harness.client.request(
        "DELETE", "/api/v1/auth/account", json={"current_password": PASSWORD, "confirm": "DELETE"}
    )
    assert res.status_code == 204
    assert asyncio.run(harness.scores.list_scores_for_owner("ada@example.com")) == []
    assert asyncio.run(harness.container.players.load_board("ada@example.com", "easy-1")) is None
    assert asyncio.run(harness.container.players.lookup(token)).authenticated is False
    assert "ada@example.com" not in harness.auth.users


@pytest.mark.spec("API-PRIV-004")
def test_public_scores_and_leaderboard_never_hold_an_email(harness: Harness) -> None:
    asyncio.run(harness.scores.record_score(_score("Ada", 9000), email="ada@example.com"))
    for path in ("/api/v1/game/scores", "/api/v1/game/leaderboard?difficulty=Easy"):
        res = harness.client.get(path)
        assert res.status_code == 200
        assert "@" not in res.text, path
        payload: Any = res.json()
        assert payload, path
