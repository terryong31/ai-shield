from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import SecretStr

from shield_api.container import build_container
from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
from shield_api.services.audit import SqliteAuditLog
from shield_api.services.players import SqlitePlayerStore
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
        json={"email": email, "password": "password123", "player_name": email.split("@")[0]},
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

    assert levels["easy"]["agent"] is None
    assert levels["easy"]["agent_tier"] is None
    assert levels["easy"]["final_node_label"] == "Help Desk"
    assert levels["medium"]["agent_tier"] == "standard"
    assert levels["hard"]["agent_tier"] == "budget"
    assert levels["medium"]["final_node_label"] == "Protected Agent"  # ENG-LEVEL-007
    assert levels["hard"]["agent"]["objective"]


@pytest.mark.spec("API-LEVEL-002")
def test_settings_pick_a_model_per_tier_and_runs_use_their_own_tier(
    harness: Harness, tmp_path: Path
) -> None:
    container = build_container(
        Settings(
            _env_file=None,
            FEEDBACK_PATH=tmp_path / "f.csv",
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
            FEEDBACK_PATH=tmp_path / "g.csv",
            SQLITE_PATH=tmp_path / "var2" / "shield.db",
        )
    )
    assert offline.game_agents == {}

    standard = ScriptedUsageChatModel(replies=[], default=HELPFUL)
    budget = ScriptedUsageChatModel(replies=[], default=HELPFUL)
    harness.container.game_agent = None
    harness.container.game_agents = {"standard": standard, "budget": budget}
    _register(harness, "tier@example.com")

    medium = _run(harness, "medium")
    assert medium.status_code == 200
    assert medium.json()["agent_mode"] == "live"
    assert standard.calls
    assert not budget.calls

    hard = _run(harness, "hard")
    assert hard.status_code == 200
    assert hard.json()["agent_mode"] == "live"
    assert budget.calls

    harness.container.game_agents = {"standard": standard}
    simulated = _run(harness, "hard")
    assert simulated.json()["agent_mode"] == "simulated"
    recorded = harness.client.get("/api/v1/game/scores", params={"level_id": "hard"}).json()
    assert len(recorded) == 1


@pytest.mark.spec("API-LEVEL-003")
def test_easy_runs_use_no_quota_and_are_recorded(harness: Harness, tmp_path: Path) -> None:
    harness.container.players = SqlitePlayerStore(tmp_path / "players.db")
    harness.container.game_agents = {
        "standard": ScriptedUsageChatModel(replies=[], default=HELPFUL)
    }

    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200
    assert [_run(harness, "easy").status_code for _ in range(3)] == [200] * 3
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 0

    _register(harness, "easy@example.com")
    runs = [_run(harness, "easy") for _ in range(7)]
    assert [r.status_code for r in runs] == [200] * 7
    assert {r.json()["agent_mode"] for r in runs} == {"none"}
    tests = [_run(harness, "easy", f"question {n}").status_code for n in range(25)]
    assert tests == [200] * 25
    session = harness.client.get("/api/v1/auth/session").json()
    assert (session["wave_runs_used"], session["test_runs_used"]) == (0, 0)

    scores = harness.client.get("/api/v1/game/scores", params={"level_id": "easy"}).json()
    assert [row["player_name"] for row in scores] == ["easy"]

    assert _run(harness, "medium").status_code == 200
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

    log = SqliteAuditLog(path)
    with sqlite3.connect(domain_path(path, "game")) as connection:
        rows = connection.execute("select id, score_version from scores").fetchall()
    assert rows == [("old", 1)]
    assert await log.list_scores(level_id="easy") == []

    level = get_level("easy")
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
    assert recorded.score_version == 2
    listed = await log.list_scores(level_id="easy")
    assert [(s.player_name, s.score_version) for s in listed] == [("newcomer", 2)]
