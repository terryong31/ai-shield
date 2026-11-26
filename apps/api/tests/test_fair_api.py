"""Scored runs, hidden prompts, spend protection and the score reset (spec 0050)."""

from __future__ import annotations

import asyncio
import itertools
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
from shield_api.services import scores as scores_module
from shield_engine.game import AgentUnavailableError, get_level
from shield_engine.ports import ChatCompletion, ChatMessage
from shield_engine.testing import ScriptedUsageChatModel

from .conftest import Harness
from .test_game_api import _valid_board_payload
from .test_train_hardening_api import _VALID_CSV

REPLY_TEXT = "Here is the answer you asked for."
SAFE_REPLY = ChatCompletion(
    text=json.dumps({"reply": REPLY_TEXT, "tool_calls": [], "refused": False}),
    input_tokens=20,
    output_tokens=5,
)
MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def _board(*checks: dict[str, Any]) -> dict[str, Any]:
    nodes = [{"id": "in", "kind": "incoming", "config": {}}, *checks]
    nodes.append({"id": "ast", "kind": "assistant", "config": {}})
    edges = [
        {
            "id": f"e{i}",
            "source": a["id"],
            "source_handle": "out" if a["kind"] in {"incoming", "text_cleanup"} else "safe",
            "target": b["id"],
        }
        for i, (a, b) in enumerate(itertools.pairwise(nodes))
    ]
    return {"nodes": nodes, "edges": edges}


# The checks of the reference board that clears easy-1 (API-GAME-002).
WORDS = _valid_board_payload()["nodes"][1:3]


def _sign_in(harness: Harness, email: str, *, paid: bool) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "player_name": email.split("@")[0]},
    )
    assert res.status_code == 200
    if paid:
        token = harness.client.cookies.get("shield_player_session")
        asyncio.run(harness.container.players.upgrade(token))


def _run(harness: Harness, level_id: str, board: dict[str, Any], **extra: Any):
    return harness.client.post(
        "/api/v1/game/run", json={"level_id": level_id, "board": board, **extra}
    )


@pytest.mark.spec("API-FAIR-001")
def test_campaign_run_response_holds_no_prompt_text_reply_or_detail(harness: Harness) -> None:
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}
    _sign_in(harness, "ada@example.com", paid=True)

    catalogue = harness.client.get("/api/v1/game/levels").text
    for level in ("easy-1", "medium-1", "hard-1"):
        for message in get_level(level).messages:
            assert message.text not in catalogue

    for level_id in ("easy-1", "medium-1"):
        res = _run(harness, level_id, _board(*WORDS))
        assert res.status_code == 200
        raw = res.text
        for message in get_level(level_id).messages:
            assert message.text not in raw
        assert REPLY_TEXT not in raw
        for trace in res.json()["traces"]:
            assert trace["text"] == ""
            assert trace["category"]
            assert all(hop["detail"] == "" for hop in trace["hops"])
            if trace["agent"] is not None:
                assert trace["agent"]["reply"] == ""


@pytest.mark.spec("API-FAIR-002")
def test_campaign_rejects_a_single_custom_message(harness: Harness) -> None:
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}
    _sign_in(harness, "ada@example.com", paid=True)

    res = _run(harness, "medium-1", _board(*WORDS), custom_message="Hello there")

    assert res.status_code == 422
    assert agent.calls == []
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 0


@pytest.mark.spec("API-FAIR-003")
def test_the_same_board_reuses_the_stored_agent_result(harness: Harness) -> None:
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}
    _sign_in(harness, "ada@example.com", paid=True)

    first = _run(harness, "medium-1", _board(*WORDS))
    calls_after_first = len(agent.calls)
    second = _run(harness, "medium-1", _board(*WORDS))

    assert first.status_code == second.status_code == 200
    assert calls_after_first > 0
    assert len(agent.calls) == calls_after_first
    assert first.json()["score"] == second.json()["score"]


class _BrokenModel:
    async def complete_with_usage(self, messages: list[ChatMessage], **_: Any) -> ChatCompletion:
        raise AgentUnavailableError("down")


@pytest.mark.spec("API-FAIR-004")
def test_a_model_failure_uses_no_run_and_a_lower_score_keeps_the_best(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com", paid=True)
    harness.container.game_agents = {"standard": _BrokenModel()}  # type: ignore[dict-item]
    failed = _run(harness, "medium-1", _board(*WORDS))
    assert failed.status_code == 503
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 0
    assert asyncio.run(harness.scores.list_scores()) == []

    best = _run(harness, "easy-1", _board(*WORDS))
    assert best.json()["score"]["won"] is True
    padded = _board(
        *WORDS,
        {"id": "l1", "kind": "length_limit", "config": {}},
        {"id": "l2", "kind": "length_limit", "config": {}},
    )
    lower = _run(harness, "easy-1", padded)
    assert lower.json()["score"]["won"] is True
    assert lower.json()["score"]["total_score"] < best.json()["score"]["total_score"]

    stored = asyncio.run(harness.scores.list_scores())
    assert [s.total_score for s in stored] == [best.json()["score"]["total_score"]]


def _record(harness: Harness, email: str, name: str, *, mastered: bool, latency: float) -> None:
    change = asyncio.run(
        harness.scores.record_score_change(
            ScoreCreateRequest(
                player_name=name,
                level_id="easy-1",
                total_score=9000,
                medal="silver",
                attacks_blocked=5,
                attacks_total=5,
                false_alarms=0,
                avg_latency_ms=latency,
                total_cost_usd=0.0,
                board=BoardGraphSchema.model_validate(_board(*WORDS)),
                won=True,
                mastered=mastered,
            ),
            email=email,
        )
    )
    asyncio.run(harness.container.leaderboard.on_score_recorded(email, change))


@pytest.mark.spec("API-FAIR-005")
def test_losses_stay_off_the_board_and_ties_sort_by_stars_then_date(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com", paid=False)
    lost = _run(harness, "easy-1", _board())
    assert lost.json()["score"]["won"] is False
    board = harness.client.get("/api/v1/game/leaderboard", params={"difficulty": "Easy"}).json()
    assert board == []

    _record(harness, "zed@example.com", "Zed", mastered=False, latency=50.0)
    time.sleep(0.002)
    _record(harness, "bob@example.com", "Bob", mastered=False, latency=90.0)
    time.sleep(0.002)
    _record(harness, "al@example.com", "Al", mastered=False, latency=1.0)
    time.sleep(0.002)
    _record(harness, "cy@example.com", "Cy", mastered=True, latency=99.0)

    board = harness.client.get("/api/v1/game/leaderboard", params={"difficulty": "Easy"}).json()
    assert [row["player_name"] for row in board] == ["Cy", "Zed", "Bob", "Al"]


@pytest.mark.spec("API-FAIR-006")
def test_version_four_scores_start_empty() -> None:
    assert scores_module.SCORE_VERSION == 4
    sql = "\n".join(p.read_text(encoding="utf-8").lower() for p in sorted(MIGRATIONS.glob("*.sql")))
    assert re.search(r"delete\s+from\s+game\.scores\s+where\s+score_version\s*<\s*4", sql)


@pytest.mark.spec("API-FAIR-007")
def test_the_daily_provider_budget_stops_runs_before_any_model_call(harness: Harness) -> None:
    from shield_api.services.spend import DAILY_PROVIDER_BUDGET_USD

    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}
    _sign_in(harness, "ada@example.com", paid=True)
    assert DAILY_PROVIDER_BUDGET_USD["paid"] == 0.10
    assert DAILY_PROVIDER_BUDGET_USD["free"] == 0.02

    ok = _run(harness, "medium-1", _board(*WORDS))
    assert ok.status_code == 200
    assert asyncio.run(harness.container.spend.spent("ada@example.com")) > 0

    asyncio.run(harness.container.spend.add("ada@example.com", 0.10))
    calls = len(agent.calls)
    blocked = _run(harness, "medium-1", _board(*WORDS))
    assert blocked.status_code == 429
    assert "resets" in blocked.json()["detail"]
    assert len(agent.calls) == calls


@pytest.mark.spec("API-FAIR-008")
def test_daily_counts_and_a_stopped_run_counts(make_harness: Any) -> None:
    from shield_api.services.players import DAILY_LIMITS, DAILY_TRAIN_LIMITS

    assert DAILY_LIMITS["paid"][0] == 50
    assert DAILY_LIMITS["free"][0] == 5
    assert DAILY_TRAIN_LIMITS == {"anonymous": 0, "free": 3, "paid": 20}

    harness = make_harness()
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}
    _sign_in(harness, "free@example.com", paid=False)
    for _ in range(5):
        assert _run(harness, "medium-1", _board(*WORDS)).status_code == 200
    assert _run(harness, "medium-1", _board(*WORDS)).status_code == 429
    for _ in range(3):
        trained = harness.client.post(
            "/api/v1/game/train", json={"algorithm": "tfidf", "csv_text": _VALID_CSV}
        )
        assert trained.status_code == 200
    again = harness.client.post(
        "/api/v1/game/train", json={"algorithm": "tfidf", "csv_text": _VALID_CSV}
    )
    assert again.status_code == 429

    stopped_harness = make_harness()
    check = ScriptedUsageChatModel(
        replies=[],
        default=ChatCompletion(
            text=json.dumps({"flagged": False, "reason": "ok"}), input_tokens=10, output_tokens=5
        ),
    )
    stopped_harness.container.check_model_for = lambda _: check  # type: ignore[assignment]
    _sign_in(stopped_harness, "slow@example.com", paid=True)
    stopped = _run(stopped_harness, "easy-5", _board({"id": "sc", "kind": "safety_check"}))
    assert stopped.status_code == 200
    assert stopped.json()["stop"]["reason"] == "time_limit"
    assert stopped_harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 1
