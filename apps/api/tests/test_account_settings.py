"""Account settings: change password and email, reset progress, delete account (spec 0025)."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shield_api.services.players import (
    InMemoryPlayerStore,
    PlayerStore,
    SupabasePlayerStore,
)
from shield_api.services.scores import (
    InMemoryScoreStore,
    ScoreStore,
    SupabaseScoreStore,
)

from .conftest import FakeClient, Harness
from .test_game_api import _valid_board_payload

COOKIE = "shield_player_session"
PASSWORD = "FirstPass1"
NEW_PASSWORD = "SecondPass2"
ACCOUNT = "/api/v1/auth/account"
MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def register(client: TestClient, email: str, password: str = PASSWORD, name: str = "Ada"):
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "player_name": name}
    )
    assert response.status_code == 200, response.text
    return response


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def change_password(client: TestClient, current: str = PASSWORD, new: str = NEW_PASSWORD):
    return client.post(
        f"{ACCOUNT}/password", json={"current_password": current, "new_password": new}
    )


def change_email(client: TestClient, new_email: str, current: str = PASSWORD):
    return client.post(
        f"{ACCOUNT}/email", json={"new_email": new_email, "current_password": current}
    )


def reset_progress(client: TestClient, current: str = PASSWORD):
    return client.post(f"{ACCOUNT}/reset-progress", json={"current_password": current})


def delete_account(client: TestClient, current: str = PASSWORD, confirm: str = "DELETE"):
    return client.request("DELETE", ACCOUNT, json={"current_password": current, "confirm": confirm})


def record_score(harness: Harness, email: str, name: str, level: str = "easy-1", total: int = 5000):
    from shield_api.schemas import ScoreCreateRequest

    asyncio.run(
        harness.scores.record_score(
            ScoreCreateRequest.model_validate(
                {
                    "player_name": name,
                    "level_id": level,
                    "total_score": total,
                    "medal": "gold",
                    "attacks_blocked": 4,
                    "attacks_total": 4,
                    "false_alarms": 0,
                    "avg_latency_ms": 4.0,
                    "total_cost_usd": 0.0,
                    "board": _valid_board_payload(),
                }
            ),
            email=email,
        )
    )


def leaderboard(client: TestClient, level: str = "easy-1") -> list[str]:
    return [
        row["player_name"] for row in client.get(f"/api/v1/game/scores?level_id={level}").json()
    ]


def save_board(harness: Harness, email: str, level: str = "easy-1") -> None:
    asyncio.run(harness.container.players.save_board(email, level, {"nodes": [level]}))


def board(harness: Harness, email: str, level: str = "easy-1") -> Any:
    return asyncio.run(harness.container.players.load_board(email, level))


def use_runs(harness: Harness, n: int) -> None:
    token = harness.client.cookies[COOKIE]
    for _ in range(n):
        asyncio.run(harness.container.players.consume_run(token, is_custom_test=False))


def session(client: TestClient) -> dict[str, Any]:
    return client.get("/api/v1/auth/session").json()


# --- password ----------------------------------------------------------------


@pytest.mark.spec("API-ACCOUNT-001")
def test_change_password_swaps_the_working_password(harness: Harness) -> None:
    register(harness.client, "ada@example.com")

    response = change_password(harness.client)

    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"
    harness.client.cookies.clear()
    assert login(harness.client, "ada@example.com").status_code == 401
    assert login(harness.client, "ada@example.com", NEW_PASSWORD).status_code == 200


@pytest.mark.spec("API-ACCOUNT-002")
def test_change_password_revokes_the_other_sessions(harness: Harness) -> None:
    register(harness.client, "ada@example.com")
    other = TestClient(harness.client.app)
    assert login(other, "ada@example.com").status_code == 200

    assert change_password(harness.client).status_code == 200

    assert session(harness.client)["authenticated"] is True
    assert session(other)["authenticated"] is False


# --- email ---------------------------------------------------------------------


@pytest.mark.spec("API-ACCOUNT-003")
def test_change_email_moves_everything_to_the_new_address(harness: Harness) -> None:
    register(harness.client, "ada@example.com")
    record_score(harness, "ada@example.com", "Ada")
    save_board(harness, "ada@example.com")
    use_runs(harness, 2)
    other = TestClient(harness.client.app)
    login(other, "ada@example.com")

    response = change_email(harness.client, "  Ada.New@Example.com ")

    assert response.status_code == 202
    assert session(harness.client)["email"] == "ada@example.com"
    harness.auth.confirm_email_change("ada.new@example.com")

    confirmed = login(harness.client, "ada.new@example.com")
    assert confirmed.status_code == 200
    assert confirmed.json()["email"] == "ada.new@example.com"
    assert confirmed.json()["wave_runs_used"] == 2
    assert session(other)["email"] == "ada.new@example.com"
    assert board(harness, "ada.new@example.com") is not None
    assert board(harness, "ada@example.com") is None
    assert leaderboard(harness.client) == ["Ada"]
    harness.client.cookies.clear()
    assert login(harness.client, "ada@example.com").status_code == 401
    assert login(harness.client, "ada.new@example.com").status_code == 200
    # The score moved too: resetting progress under the new email removes it.
    assert reset_progress(harness.client).json()["scores_removed"] == 1


@pytest.mark.spec("API-ACCOUNT-004")
def test_change_email_refuses_a_taken_or_unchanged_address(harness: Harness) -> None:
    register(TestClient(harness.client.app), "grace@example.com", name="Grace")
    register(harness.client, "ada@example.com")

    taken = change_email(harness.client, "grace@example.com")
    same = change_email(harness.client, "ADA@example.com")

    assert taken.status_code == 409
    assert same.status_code == 422
    assert session(harness.client)["email"] == "ada@example.com"
    assert login(TestClient(harness.client.app), "grace@example.com").status_code == 200


@pytest.mark.spec("API-ACCOUNT-005")
def test_moving_onto_leftover_usage_keeps_the_larger_count(harness: Harness) -> None:
    register(harness.client, "old@example.com", name="Old")
    use_runs(harness, 3)
    assert delete_account(harness.client).status_code == 204
    register(harness.client, "ada@example.com")
    use_runs(harness, 1)

    response = change_email(harness.client, "old@example.com")
    assert response.status_code == 202
    harness.auth.confirm_email_change("old@example.com")
    signed_in = login(harness.client, "old@example.com")

    assert signed_in.status_code == 200
    assert signed_in.json()["wave_runs_used"] == 3


# --- reset progress ------------------------------------------------------------


@pytest.mark.spec("API-ACCOUNT-006")
def test_reset_progress_removes_scores_and_boards_only(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(allow_self_upgrade=True)
    register(harness.client, "ada@example.com")
    assert harness.client.post("/api/v1/auth/upgrade").status_code == 200
    record_score(harness, "ada@example.com", "Ada", "easy-1")
    record_score(harness, "ada@example.com", "Ada", "medium-1")
    save_board(harness, "ada@example.com", "easy-1")
    use_runs(harness, 2)

    response = reset_progress(harness.client)

    assert response.status_code == 200
    assert response.json() == {"scores_removed": 2, "boards_removed": 1}
    assert leaderboard(harness.client) == []
    assert board(harness, "ada@example.com") is None
    after = session(harness.client)
    assert (after["authenticated"], after["tier"], after["wave_runs_used"]) == (True, "paid", 2)


@pytest.mark.spec("API-ACCOUNT-007")
def test_reset_progress_never_touches_another_players_score(harness: Harness) -> None:
    other = TestClient(harness.client.app)
    register(other, "twin@example.com", name="Ada")
    record_score(harness, "twin@example.com", "Ada", total=4000)
    asyncio.run(_record_legacy_score(harness.scores))
    register(harness.client, "ada@example.com", name="Ada")
    record_score(harness, "ada@example.com", "Ada", total=6000)
    assert leaderboard(harness.client) == ["Ada", "Ada", "Legacy"]

    assert reset_progress(harness.client).json()["scores_removed"] == 1

    rows = harness.client.get("/api/v1/game/scores?level_id=easy-1").json()
    assert [(r["player_name"], r["total_score"]) for r in rows] == [("Ada", 4000), ("Legacy", 100)]


async def _record_legacy_score(scores: ScoreStore) -> None:
    from shield_api.schemas import ScoreCreateRequest

    await scores.record_score(
        ScoreCreateRequest.model_validate(
            {
                "player_name": "Legacy",
                "level_id": "easy-1",
                "total_score": 100,
                "medal": "none",
                "attacks_blocked": 0,
                "attacks_total": 4,
                "false_alarms": 0,
                "avg_latency_ms": 9.0,
                "total_cost_usd": 0.0,
                "board": _valid_board_payload(),
            }
        )
    )


# --- delete account ------------------------------------------------------------


@pytest.mark.spec("API-ACCOUNT-008")
def test_delete_account_removes_the_account_and_its_data(harness: Harness) -> None:
    register(harness.client, "ada@example.com")
    record_score(harness, "ada@example.com", "Ada")
    save_board(harness, "ada@example.com")
    other = TestClient(harness.client.app)
    login(other, "ada@example.com")

    response = delete_account(harness.client)

    assert response.status_code == 204
    header = response.headers.get("set-cookie", "").lower()
    assert header.startswith(f"{COOKIE}=")
    assert "max-age=0" in header or "expires=thu, 01 jan 1970" in header
    assert session(other)["authenticated"] is False
    assert leaderboard(harness.client) == []
    assert board(harness, "ada@example.com") is None
    assert login(harness.client, "ada@example.com").status_code == 401


@pytest.mark.spec("API-ACCOUNT-009")
def test_deleting_and_registering_again_does_not_reset_the_quota(harness: Harness) -> None:
    register(harness.client, "ada@example.com")
    use_runs(harness, 2)
    delete_account(harness.client)

    again = register(harness.client, "ada@example.com")

    assert again.json()["wave_runs_used"] == 2


@pytest.mark.spec("API-ACCOUNT-010")
@pytest.mark.parametrize("confirm", ["delete", "DELETE ", "", "yes"])
def test_delete_needs_the_exact_confirmation(harness: Harness, confirm: str) -> None:
    register(harness.client, "ada@example.com")

    assert delete_account(harness.client, confirm=confirm).status_code == 422
    assert session(harness.client)["email"] == "ada@example.com"


# --- errors and safety ---------------------------------------------------------


def _all_calls(client: TestClient) -> list[Any]:
    return [
        change_password(client),
        change_email(client, "new@example.com"),
        reset_progress(client),
        delete_account(client),
    ]


@pytest.mark.spec("API-ACCOUNT-011")
def test_account_endpoints_need_a_signed_in_player(harness: Harness) -> None:
    assert {r.status_code for r in _all_calls(harness.client)} == {403}
    harness.client.cookies.set(COOKIE, "not-a-session")
    assert {r.status_code for r in _all_calls(harness.client)} == {403}
    harness.client.cookies.clear()
    harness.client.post("/api/v1/auth/anonymous")
    responses = _all_calls(harness.client)
    assert {r.status_code for r in responses} == {403}
    assert {r.json()["detail"] for r in responses} == {"Sign in to manage your account."}


@pytest.mark.spec("API-ACCOUNT-012")
def test_a_wrong_password_changes_nothing_and_is_rate_limited(harness: Harness) -> None:
    register(harness.client, "ada@example.com")
    record_score(harness, "ada@example.com", "Ada")
    wrong = "not my password"

    responses = [
        change_password(harness.client, current=wrong),
        change_email(harness.client, "new@example.com", current=wrong),
        reset_progress(harness.client, current=wrong),
        delete_account(harness.client, current=wrong),
    ]

    assert {r.status_code for r in responses} == {401}
    assert session(harness.client)["email"] == "ada@example.com"
    assert leaderboard(harness.client) == ["Ada"]
    assert reset_progress(harness.client, current=wrong).status_code == 401
    assert reset_progress(harness.client).status_code == 429
    harness.clock.advance(harness.container.settings.CLEARANCE_WINDOW_MINUTES * 60 + 1)
    assert reset_progress(harness.client).status_code == 200


@pytest.mark.spec("API-AUTH-001")
@pytest.mark.spec("API-ACCOUNT-013")
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/password", {"current_password": PASSWORD}),
        ("POST", "/password", {"current_password": PASSWORD, "new_password": "12345"}),
        ("POST", "/password", {"current_password": PASSWORD, "new_password": "alllowercase1"}),
        ("POST", "/password", {"current_password": PASSWORD, "new_password": "ALLUPPERCASE1"}),
        ("POST", "/password", {"current_password": PASSWORD, "new_password": "NoDigitsHere"}),
        ("POST", "/password", {"current_password": PASSWORD, "new_password": PASSWORD}),
        ("POST", "/email", {"new_email": "not-an-email", "current_password": PASSWORD}),
        ("POST", "/email", {"current_password": PASSWORD}),
        ("POST", "/reset-progress", {"current_password": PASSWORD, "extra": 1}),
        ("DELETE", "", {"current_password": PASSWORD}),
    ],
)
def test_invalid_bodies_are_rejected(
    harness: Harness, method: str, path: str, body: dict[str, Any]
) -> None:
    register(harness.client, "ada@example.com")

    response = harness.client.request(method, f"{ACCOUNT}{path}", json=body)

    assert response.status_code == 422
    assert login(TestClient(harness.client.app), "ada@example.com").status_code == 200


@pytest.mark.spec("API-ACCOUNT-014")
def test_no_password_is_echoed_or_logged(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    register(harness.client, "ada@example.com")
    responses = [
        change_password(harness.client, current="wrong one"),
        change_password(harness.client),
        change_email(harness.client, "new@example.com", current=NEW_PASSWORD),
        reset_progress(harness.client, current=NEW_PASSWORD),
        delete_account(harness.client, current=NEW_PASSWORD),
    ]
    assert [r.status_code for r in responses] == [401, 200, 202, 200, 204]
    bodies = [r.text for r in responses]

    for secret in (PASSWORD, NEW_PASSWORD, "wrong one"):
        assert secret not in caplog.text
        assert all(secret not in body for body in bodies)
    assert all("password_hash" not in body and "salt" not in body for body in bodies)


class ExplodingMoves(InMemoryPlayerStore):
    async def move_email(self, old: str, new: str) -> None:
        raise RuntimeError("database went away")

    async def delete_account(self, email: str) -> None:
        raise RuntimeError("database went away")


@pytest.mark.spec("API-ACCOUNT-015")
def test_a_store_failure_midway_leaves_the_old_login_working(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(players=ExplodingMoves())
    register(harness.client, "ada@example.com")

    assert change_email(harness.client, "new@example.com").status_code == 202
    harness.auth.confirm_email_change("new@example.com")
    moved = login(harness.client, "new@example.com")
    user = harness.auth.by_email("new@example.com")
    assert user is not None
    user.email = "ada@example.com"
    deleted = delete_account(harness.client)

    assert moved.status_code == deleted.status_code == 503
    assert "database" not in moved.text + deleted.text
    fresh = TestClient(harness.client.app)
    assert login(fresh, "ada@example.com").status_code == 200


# --- storage -------------------------------------------------------------------


def _run_sequence(harness: Harness) -> list[Any]:
    client = harness.client
    register(client, "ada@example.com")
    record_score(harness, "ada@example.com", "Ada")
    save_board(harness, "ada@example.com")
    use_runs(harness, 1)
    other = TestClient(client.app)
    login(other, "ada@example.com")
    steps: list[Any] = [
        change_password(client).json()["email"],
        session(other)["authenticated"],
    ]
    assert change_email(client, "new@example.com", current=NEW_PASSWORD).status_code == 202
    harness.auth.confirm_email_change("new@example.com")
    steps += [
        login(client, "new@example.com", NEW_PASSWORD).json()["wave_runs_used"],
        board(harness, "new@example.com") is not None,
        reset_progress(client, current=NEW_PASSWORD).json(),
    ]
    record_score(harness, "new@example.com", "Ada")
    steps += [
        delete_account(client, current=NEW_PASSWORD).status_code,
        leaderboard(client),
        login(client, "new@example.com", NEW_PASSWORD).status_code,
        register(client, "new@example.com").json()["wave_runs_used"],
    ]
    return steps


@pytest.mark.spec("API-ACCOUNT-016")
def test_every_store_behaves_the_same(make_harness: Callable[..., Harness], fake_supabase) -> None:
    client: FakeClient = fake_supabase()
    stores: list[tuple[PlayerStore, ScoreStore]] = [
        (InMemoryPlayerStore(), InMemoryScoreStore()),
        (SupabasePlayerStore(client), SupabaseScoreStore(client)),
    ]

    results = [_run_sequence(make_harness(players=p, scores=s)) for p, s in stores]

    assert results[0] == [
        "ada@example.com",
        False,
        1,
        True,
        {"scores_removed": 1, "boards_removed": 1},
        204,
        [],
        401,
        1,
    ]
    assert results[1] == results[0]


@pytest.mark.spec("API-ACCOUNT-017")
def test_scores_are_owned_by_email(make_harness: Callable[..., Harness], fake_supabase) -> None:
    sql = "\n".join(p.read_text(encoding="utf-8").lower() for p in sorted(MIGRATIONS.glob("*.sql")))
    assert "alter table game.scores add column if not exists email text" in sql
    assert "on game.scores (email, level_id, score_version)" in sql

    client: FakeClient = fake_supabase()
    harness = make_harness(scores=SupabaseScoreStore(client))
    register(harness.client, "ada@example.com")
    record_score(harness, "ada@example.com", "Ada", total=1000)
    record_score(harness, "ada@example.com", "Ada", total=3000)
    record_score(harness, "ada@example.com", "Ada", total=2000)

    rows = [(r["email"], r["total_score"]) for r in client.tables[("game", "scores")].rows]
    assert rows == [("ada@example.com", 3000)]


@pytest.mark.spec("API-ACCOUNT-018")
def test_the_leaderboard_never_shows_emails(
    make_harness: Callable[..., Harness], fake_supabase
) -> None:
    client: FakeClient = fake_supabase()
    harness = make_harness(scores=SupabaseScoreStore(client))
    register(harness.client, "ada@example.com")
    record_score(harness, "ada@example.com", "Ada")
    assert [r["email"] for r in client.tables[("game", "scores")].rows] == ["ada@example.com"]

    response = harness.client.get("/api/v1/game/scores")

    assert "ada@example.com" not in response.text
    assert all("email" not in row for row in response.json())


# --- Supabase Auth (spec 0027) ---------------------------------------------------


def supabase_harness(make_harness: Callable[..., Harness]) -> Harness:
    harness = make_harness()
    harness.auth.confirm_email = False
    register(harness.client, "ada@example.com")
    harness.auth.calls.clear()
    return harness


@pytest.mark.spec("API-ACCOUNT-019")
def test_supabase_password_change(make_harness: Callable[..., Harness]) -> None:
    harness = supabase_harness(make_harness)

    assert change_password(harness.client).status_code == 200

    assert harness.auth.calls == ["sign_in_with_password", "sign_out", "admin.update_user_by_id"]
    assert harness.auth.open_sessions == 0
    fresh = TestClient(harness.client.app)
    assert login(fresh, "ada@example.com").status_code == 401
    assert login(fresh, "ada@example.com", NEW_PASSWORD).status_code == 200
    store = harness.container.players
    assert isinstance(store, InMemoryPlayerStore)
    assert not hasattr(store._accounts["ada@example.com"], "password_hash")


@pytest.mark.spec("API-ACCOUNT-020")
def test_supabase_email_change(make_harness: Callable[..., Harness]) -> None:
    harness = supabase_harness(make_harness)
    harness.auth.add("grace@example.com", "grace password")

    taken = change_email(harness.client, "grace@example.com")
    requested = change_email(harness.client, "new@example.com")

    assert taken.status_code == 409
    assert requested.status_code == 202
    assert harness.auth.by_email("ada@example.com") is not None
    assert harness.auth.by_email("new@example.com") is None

    harness.auth.confirm_email_change("new@example.com")
    moved = login(harness.client, "new@example.com")
    assert moved.status_code == 200
    assert harness.auth.by_email("new@example.com") is not None
    assert harness.auth.by_email("ada@example.com") is None

    failing = make_harness(players=ExplodingMoves())
    failing.auth.confirm_email = False
    register(failing.client, "ada@example.com")
    assert change_email(failing.client, "new@example.com").status_code == 202
    failing.auth.confirm_email_change("new@example.com")
    assert login(failing.client, "new@example.com").status_code == 503


@pytest.mark.spec("API-ACCOUNT-021")
def test_supabase_delete(make_harness: Callable[..., Harness]) -> None:
    harness = supabase_harness(make_harness)

    assert delete_account(harness.client).status_code == 204
    assert harness.auth.calls[-1] == "admin.delete_user"
    assert harness.auth.by_email("ada@example.com") is None
    assert login(TestClient(harness.client.app), "ada@example.com").status_code == 401

    failing = supabase_harness(make_harness)
    failing.auth.fail_admin = True
    assert delete_account(failing.client).status_code == 503
