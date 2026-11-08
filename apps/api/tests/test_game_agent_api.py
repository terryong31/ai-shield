from __future__ import annotations

import json
from pathlib import Path

import pytest

from shield_api.services.players import QuotaExceededError, SqlitePlayerStore
from shield_engine.ports import ChatCompletion
from shield_engine.testing import ScriptedUsageChatModel

from .conftest import Harness

HELPFUL = ChatCompletion(
    text=json.dumps({"reply": "Happy to help.", "tool_calls": [], "refused": False}),
    input_tokens=100,
    output_tokens=20,
)


def _board(*, with_blocked: bool = False) -> dict:
    nodes = [
        {"id": "in", "kind": "incoming", "config": {}},
        {"id": "wf", "kind": "word_filter", "config": {}},
        {"id": "ast", "kind": "assistant", "config": {"rules": ["Never share codes."]}},
    ]
    edges = [
        {"id": "e1", "source": "in", "source_handle": "out", "target": "wf"},
        {"id": "e2", "source": "wf", "source_handle": "safe", "target": "ast"},
    ]
    if with_blocked:
        nodes.append({"id": "blk", "kind": "blocked", "config": {}})
        edges.append({"id": "e3", "source": "wf", "source_handle": "block", "target": "blk"})
    return {"nodes": nodes, "edges": edges}


def _wave(harness: Harness) -> int:
    response = harness.client.post(
        "/api/v1/game/run", json={"level_id": "medium", "board": _board()}
    )
    return response.status_code


def _test(harness: Harness, n: int) -> int:
    response = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "medium", "board": _board(), "custom_message": f"question {n}"},
    )
    return response.status_code


def _register(harness: Harness, email: str) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "player_name": email.split("@")[0]},
    )
    assert res.status_code == 200


@pytest.mark.spec("API-AGENT-001")
async def test_daily_limits_are_one_five_and_three_hundred_waves_by_tier(
    harness: Harness, tmp_path: Path
) -> None:
    store = SqlitePlayerStore(tmp_path / "players.db")
    harness.container.players = store

    # Anonymous: 1 wave and 3 tests per day
    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200
    anon = harness.client.get("/api/v1/auth/session").json()
    assert (anon["daily_wave_limit"], anon["daily_test_limit"]) == (1, 3)
    assert _wave(harness) == 200
    assert _wave(harness) == 429
    assert [_test(harness, n) for n in range(4)] == [200, 200, 200, 429]

    # Free: 5 waves and 20 tests per day
    _register(harness, "free@example.com")
    assert [_wave(harness) for _ in range(6)] == [200] * 5 + [429]
    assert [_test(harness, n) for n in range(21)] == [200] * 20 + [429]
    limited = harness.client.post(
        "/api/v1/game/run", json={"level_id": "medium", "board": _board()}
    )
    assert "Upgrade" in limited.json()["detail"]

    # Paid: 300 waves and 1000 tests per day
    _register(harness, "paid@example.com")
    paid = harness.client.post("/api/v1/auth/upgrade").json()
    assert (paid["daily_wave_limit"], paid["daily_test_limit"]) == (300, 1000)
    token = harness.client.cookies.get("shield_player_session")
    for _ in range(300):
        await store.consume_run(token, is_custom_test=False)
    with pytest.raises(QuotaExceededError):
        await store.consume_run(token, is_custom_test=False)


@pytest.mark.spec("API-AGENT-002")
def test_provider_failure_returns_503_without_consuming_quota_or_recording(
    harness: Harness, tmp_path: Path
) -> None:
    harness.container.players = SqlitePlayerStore(tmp_path / "players.db")
    harness.container.game_agent = ScriptedUsageChatModel(replies=[RuntimeError("down")])
    _register(harness, "ada@example.com")

    response = harness.client.post(
        "/api/v1/game/run", json={"level_id": "medium", "board": _board()}
    )
    assert response.status_code == 503

    session = harness.client.get("/api/v1/auth/session").json()
    assert session["wave_runs_used"] == 0
    assert harness.client.get("/api/v1/game/scores").json() == []


@pytest.mark.spec("API-AGENT-003")
def test_only_live_agent_runs_are_recorded_on_the_leaderboard(
    harness: Harness, tmp_path: Path
) -> None:
    harness.container.players = SqlitePlayerStore(tmp_path / "players.db")
    _register(harness, "grace@example.com")

    simulated = harness.client.post(
        "/api/v1/game/run", json={"level_id": "medium", "board": _board()}
    )
    assert simulated.status_code == 200
    assert simulated.json()["agent_mode"] == "simulated"
    assert harness.client.get("/api/v1/game/scores").json() == []

    harness.container.game_agent = ScriptedUsageChatModel(replies=[], default=HELPFUL)
    live = harness.client.post("/api/v1/game/run", json={"level_id": "medium", "board": _board()})
    assert live.status_code == 200
    assert live.json()["agent_mode"] == "live"
    scores = harness.client.get("/api/v1/game/scores").json()
    assert [row["player_name"] for row in scores] == ["grace"]


@pytest.mark.spec("API-AGENT-004")
def test_levels_expose_agent_profile_and_runs_return_agent_results(harness: Harness) -> None:
    levels = harness.client.get("/api/v1/game/levels")
    assert levels.status_code == 200
    for level in levels.json()["levels"]:
        agent = level["agent"]
        if agent is None:  # Easy is classification only (spec 0021)
            continue
        assert agent["objective"]
        assert agent["token_budget"] > 0
        assert {"name", "description", "allowed"} <= set(agent["tools"][0])
        assert any(not tool["allowed"] for tool in agent["tools"])
    assert "Confidential value" not in levels.text
    assert "CANARY" not in levels.text.upper()

    harness.container.game_agent = ScriptedUsageChatModel(replies=[], default=HELPFUL)
    run = harness.client.post("/api/v1/game/run", json={"level_id": "medium", "board": _board()})
    assert run.status_code == 200
    body = run.json()
    assert body["agent_mode"] == "live"
    reached = [t for t in body["traces"] if t["agent"] is not None]
    assert reached
    assert {
        "reply",
        "tool_calls",
        "refused",
        "verdict",
        "input_tokens",
        "output_tokens",
        "estimated_tokens",
        "latency_ms",
    } <= set(reached[0]["agent"])
    assert {
        "protection_points",
        "helpfulness_points",
        "tool_points",
        "token_points",
        "speed_points",
        "cost_points",
        "leak_penalty",
        "total_tokens",
    } <= set(body["score"])
    assert body["score"]["total_tokens"] == 120 * len(reached)


@pytest.mark.spec("API-AGENT-005")
def test_board_with_retired_blocked_node_is_rejected_with_422(harness: Harness) -> None:
    response = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "medium", "board": _board(with_blocked=True)},
    )
    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Remove the Blocked node; unreached prompts are blocked automatically."
    )
