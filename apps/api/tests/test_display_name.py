"""Display name changes (spec 0048)."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shield_api.services.leaderboard import LeaderboardService
from shield_api.services.players import SupabasePlayerStore
from shield_api.services.scores import InMemoryScoreStore, SupabaseScoreStore

from .conftest import FakeClient, Harness
from .test_account_settings import leaderboard, login, record_score, register, session
from .test_auth_flows_and_hardening import _prod_container
from .test_leaderboard_scaling import FakeLeaderboardRedis, _req

PROFILE = "/api/v1/auth/account/profile"


def record_win(harness: Harness, email: str, name: str) -> None:
    asyncio.run(harness.scores.record_score(_req(name, level_id="easy-1"), email=email))


def rename(client: TestClient, name: Any, headers: dict[str, str] | None = None) -> Any:
    return client.patch(PROFILE, json={"player_name": name}, headers=headers)


@pytest.mark.spec("API-NAME-001")
def test_rename_updates_the_session_and_the_other_devices(harness: Harness) -> None:
    register(harness.client, "ada@example.com")
    other = TestClient(harness.client.app)
    login(other, "ada@example.com")

    response = rename(harness.client, "  Countess Ada ")

    assert response.status_code == 200
    assert response.json()["player_name"] == "Countess Ada"
    assert session(harness.client)["player_name"] == "Countess Ada"
    assert session(other)["player_name"] == "Countess Ada"


@pytest.mark.spec("API-NAME-001")
async def test_supabase_rename_updates_account_and_sessions(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    client = fake_supabase()
    accounts = client.schema("players").table("accounts")
    sessions = client.schema("players").table("sessions")
    accounts.rows = [
        {"email": "ada@example.com", "player_name": "Ada", "tier": "free"},
        {"email": "twin@example.com", "player_name": "Ada", "tier": "free"},
    ]
    sessions.rows = [{"token_hash": "x", "email": "ada@example.com", "player_name": "Ada"}]

    await SupabasePlayerStore(client).set_player_name("ada@example.com", "Countess")

    assert [r["player_name"] for r in accounts.rows] == ["Countess", "Ada"]
    assert sessions.rows[0]["player_name"] == "Countess"


@pytest.mark.spec("API-NAME-002")
def test_rename_moves_scores_to_the_new_name_and_keeps_rank(harness: Harness) -> None:
    redis = FakeLeaderboardRedis()
    harness.container.leaderboard = LeaderboardService(harness.container.scores, redis)
    register(harness.client, "ada@example.com")
    record_win(harness, "ada@example.com", "Ada")
    me = "/api/v1/game/leaderboard/me?difficulty=Easy"
    board = "/api/v1/game/leaderboard?difficulty=Easy"
    assert harness.client.get(board).json()[0]["player_name"] == "Ada"
    before = harness.client.get(me).json()

    assert rename(harness.client, "Countess").status_code == 200

    assert harness.client.get(board).json()[0]["player_name"] == "Countess"
    assert harness.client.get(me).json() == before
    assert leaderboard(harness.client) == ["Countess"]


@pytest.mark.spec("API-NAME-003")
def test_rename_does_not_touch_another_player_with_the_same_name(harness: Harness) -> None:
    other = TestClient(harness.client.app)
    register(other, "twin@example.com", name="Ada")
    record_score(harness, "twin@example.com", "Ada", total=4000)
    register(harness.client, "ada@example.com", name="Ada")
    record_score(harness, "ada@example.com", "Ada", total=6000)

    assert rename(harness.client, "Countess").status_code == 200

    assert leaderboard(harness.client) == ["Countess", "Ada"]
    assert session(other)["player_name"] == "Ada"


@pytest.mark.spec("API-NAME-003")
async def test_supabase_score_rename_is_by_email(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    client = fake_supabase()
    table = client.schema("game").table("scores")
    table.rows = [
        {"email": "ada@example.com", "player_name": "Ada"},
        {"email": "twin@example.com", "player_name": "Ada"},
        {"email": None, "player_name": "Ada"},
    ]

    await SupabaseScoreStore(client).rename_scores_player("ada@example.com", "Countess")

    assert [r["player_name"] for r in table.rows] == ["Countess", "Ada", "Ada"]


@pytest.mark.spec("API-NAME-004")
def test_rename_needs_a_signed_in_player(harness: Harness) -> None:
    assert rename(harness.client, "Ada").status_code == 403
    harness.client.post("/api/v1/auth/anonymous")
    assert rename(harness.client, "Ada").status_code == 403


@pytest.mark.spec("API-NAME-004")
@pytest.mark.parametrize(
    "name", ["", "   ", "x" * 65, "a\nb", "a\u0000b", "a‮b", "a⁦b", "a​b", 7, None]
)
def test_rename_refuses_invalid_names(harness: Harness, name: Any) -> None:
    register(harness.client, "ada@example.com")

    assert rename(harness.client, name).status_code == 422
    assert session(harness.client)["player_name"] == "Ada"


@pytest.mark.spec("API-NAME-005")
def test_rename_is_rate_limited_in_production() -> None:
    client, _, _, _ = _prod_container(confirm_email=False)
    headers = {
        "x-shield-client-ip": "203.0.113.9",
        "x-shield-proxy-secret": SecretStr("s3cret").get_secret_value(),
        "x-shield-botid": "pass",
        "sec-fetch-site": "same-origin",
    }
    signed_up = client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": "StrongPass1", "player_name": "Ada"},
        headers=headers,
    )
    assert signed_up.status_code == 200, signed_up.text

    codes = [rename(client, f"Ada {i}", headers) for i in range(6)]

    assert [r.status_code for r in codes] == [200] * 5 + [429]
    assert int(codes[-1].headers["Retry-After"]) > 0


@pytest.mark.spec("API-NAME-006")
def test_redis_failure_does_not_fail_the_rename_and_the_board_rebuilds(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(harness.container.scores, redis)
    harness.container.leaderboard = service
    register(harness.client, "ada@example.com")
    record_win(harness, "ada@example.com", "Ada")
    board = "/api/v1/game/leaderboard?difficulty=Easy"
    assert harness.client.get(board).json()[0]["player_name"] == "Ada"

    async def broken(*_: Any) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(service, "_eval_script", broken)
    response = rename(harness.client, "Countess")
    monkeypatch.undo()

    assert response.status_code == 200
    assert harness.client.get(board).json()[0]["player_name"] == "Countess"


@pytest.mark.spec("API-NAME-006")
def test_store_failure_is_a_503(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    register(harness.client, "ada@example.com")

    async def broken(self: Any, email: str, name: str) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(InMemoryScoreStore, "rename_scores_player", broken)
    assert rename(harness.client, "Countess").status_code == 503
    monkeypatch.undo()
    assert rename(harness.client, "Countess").status_code == 200
    assert asyncio.run(harness.scores.list_scores_for_owner("ada@example.com")) == []
