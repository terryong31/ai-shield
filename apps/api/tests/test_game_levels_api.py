from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import SecretStr

from shield_api.container import build_container
from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
from shield_api.services.players import SqlitePlayerStore
from shield_api.services.scores import SqliteScoreStore
from shield_api.services.sqlite import domain_path
from shield_api.settings import Settings
from shield_engine.game import get_level
from shield_engine.ports import ChatCompletion
from shield_engine.testing import ScriptedUsageChatModel

from .conftest import Harness

HELPFUL = ChatCompletion(
    text=json.dumps({"reply": "Happy to help.", "tool_calls": [], "refused": False}),
    input_tokens=40,
    output_tokens=10,
)


def _board() -> dict:
    return {
        "nodes": [
            {"id": "in", "kind": "incoming", "config": {}},
            {"id": "wf", "kind": "word_filter", "config": {}},
            {"id": "ast", "kind": "assistant", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "source_handle": "out", "target": "wf"},
            {"id": "e2", "source": "wf", "source_handle": "safe", "target": "ast"},
        ],
    }


def _register(harness: Harness, email: str) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "player_name": email.split("@")[0]},
    )
    assert res.status_code == 200


def _run(harness: Harness, level_id: str, message: str | None = None):
    body: dict = {"level_id": level_id, "board": _board()}
    if message is not None:
        body["custom_message"] = message
    return harness.client.post("/api/v1/game/run", json=body)


@pytest.mark.spec("API-LEVEL-001")
def test_catalog_exposes_model_tier_and_final_node_label(harness: Harness) -> None:
    levels = {lvl["id"]: lvl for lvl in harness.client.get("/api/v1/game/levels").json()["levels"]}

    assert levels["easy-1"]["agent"] is None
    assert levels["easy-1"]["agent_tier"] is None
    assert levels["easy-1"]["final_node_label"] == "Help Desk"
    assert levels["medium-1"]["agent_tier"] == "standard"
    assert levels["hard-1"]["agent_tier"] == "budget"
    assert levels["medium-1"]["final_node_label"] == "Protected Agent"  # ENG-LEVEL-007
    assert levels["hard-1"]["agent"]["objective"]


@pytest.mark.spec("API-LEVEL-002")
def test_settings_pick_a_model_per_tier_and_runs_use_their_own_tier(
    harness: Harness, tmp_path: Path
) -> None:
    container = build_container(
        Settings(
            _env_file=None,
            SQLITE_PATH=tmp_path / "var" / "shield.db",
            GROQ_API_KEY=SecretStr("gsk-test"),
            GOOGLE_API_KEY=SecretStr("g-test"),
            GAME_MODEL_STANDARD="gemini-test-standard",
            GAME_MODEL_BUDGET="llama-3.1-8b-instant",
        )
    )
    assert getattr(container.game_agents["standard"], "model", None) == "gemini-test-standard"
    assert getattr(container.game_agents["budget"], "model", None) == "llama-3.1-8b-instant"

    offline = build_container(
        Settings(
            _env_file=None,
            SQLITE_PATH=tmp_path / "var2" / "shield.db",
        )
    )
    assert offline.game_agents == {}

    standard = ScriptedUsageChatModel(replies=[], default=HELPFUL)
    budget = ScriptedUsageChatModel(replies=[], default=HELPFUL)
    harness.container.game_agent = None
    harness.container.game_agents = {"standard": standard, "budget": budget}
    _register(harness, "tier@example.com")
    assert harness.client.post("/api/v1/auth/upgrade").status_code == 200

    medium = _run(harness, "medium-1")
    assert medium.status_code == 200
    assert medium.json()["agent_mode"] == "live"
    assert standard.calls
    assert not budget.calls

    hard = _run(harness, "hard-1")
    assert hard.status_code == 200
    assert hard.json()["agent_mode"] == "live"
    assert budget.calls

    harness.container.game_agents = {"standard": standard}
    simulated = _run(harness, "hard-1")
    assert simulated.json()["agent_mode"] == "simulated"
    recorded = harness.client.get("/api/v1/game/scores", params={"level_id": "hard-1"}).json()
    assert len(recorded) == 1


@pytest.mark.spec("API-LEVEL-003")
def test_easy_runs_use_no_quota_and_are_recorded(harness: Harness, tmp_path: Path) -> None:
    harness.container.players = SqlitePlayerStore(tmp_path / "players.db")
    harness.container.game_agents = {
        "standard": ScriptedUsageChatModel(replies=[], default=HELPFUL)
    }

    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200
    assert [_run(harness, "easy-1").status_code for _ in range(3)] == [200] * 3
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 0

    _register(harness, "easy@example.com")
    runs = [_run(harness, "easy-1") for _ in range(7)]
    assert [r.status_code for r in runs] == [200] * 7
    assert {r.json()["agent_mode"] for r in runs} == {"none"}
    tests = [_run(harness, "easy-1", f"question {n}").status_code for n in range(25)]
    assert tests == [200] * 25
    session = harness.client.get("/api/v1/auth/session").json()
    assert (session["wave_runs_used"], session["test_runs_used"]) == (0, 0)

    scores = harness.client.get("/api/v1/game/scores", params={"level_id": "easy-1"}).json()
    assert [row["player_name"] for row in scores] == ["easy"]

    assert _run(harness, "medium-1").status_code == 200
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 1


@pytest.mark.spec("API-LEVEL-004")
async def test_leaderboard_lists_only_the_current_score_version(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    # A pre-0021 leaderboard table in the game domain database (spec 0024 layout).
    with sqlite3.connect(domain_path(path, "game")) as connection:
        connection.execute(
            """
            create table scores (
              id text primary key, created_at text not null, player_name text not null,
              level_id text not null, total_score integer not null, medal text not null,
              attacks_blocked integer not null, attacks_total integer not null,
              false_alarms integer not null, avg_latency_ms real not null,
              total_cost_usd real not null, board_json text not null
            )
            """
        )
        connection.execute(
            "insert into scores values ('old', '2026-01-01T00:00:00+00:00', 'veteran', 'easy',"
            " 9999, 'gold', 4, 4, 0, 1.0, 0.0, ?)",
            (json.dumps({"nodes": [], "edges": []}),),
        )

    log = SqliteScoreStore(path)
    # Spec 0039 purges pre-v3 / legacy 'easy' rows on startup, and list_scores filters by version.
    with sqlite3.connect(domain_path(path, "game")) as connection:
        assert connection.execute("select id from scores").fetchall() == []
        connection.execute(
            "insert into scores (id, created_at, player_name, level_id, total_score, medal,"
            " attacks_blocked, attacks_total, false_alarms, avg_latency_ms, total_cost_usd,"
            " board_json, score_version, email, won, mastered)"
            " values ('v2-row', '2026-06-01T00:00:00+00:00', 'veteran', 'easy-1',"
            " 9999, 'gold', 4, 4, 0, 1.0, 0.0, ?, 2, 'vet@example.com', 1, 0)",
            (json.dumps({"nodes": [], "edges": []}),),
        )
    assert await log.list_scores(level_id="easy-1") == []

    level = get_level("easy-1")
    recorded = await log.record_score(
        ScoreCreateRequest(
            player_name="newcomer",
            level_id=level.id,
            total_score=5000,
            medal="bronze",
            attacks_blocked=2,
            attacks_total=4,
            false_alarms=0,
            avg_latency_ms=1.0,
            total_cost_usd=0.0,
            board=BoardGraphSchema(nodes=[], edges=[]),
        )
    )
    assert recorded.score_version == 3
    listed = await log.list_scores(level_id="easy-1")
    assert [(s.player_name, s.score_version) for s in listed] == [("newcomer", 3)]
