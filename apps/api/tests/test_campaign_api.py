from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
from shield_api.services.scores import (
    SCORE_VERSION,
    InMemoryScoreStore,
    SupabaseScoreStore,
)
from shield_engine.ports import ChatCompletion
from shield_engine.testing import ScriptedUsageChatModel

from .conftest import FakeClient, Harness

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "supabase" / "migrations"


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


def _register(harness: Harness, email: str, name: str | None = None) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123",
            "player_name": name or email.split("@")[0],
        },
    )
    assert res.status_code == 200


@pytest.mark.spec("API-CAMP-001")
def test_catalog_exposes_19_levels_and_enforces_pro_tier_gating(make_harness) -> None:
    harness = make_harness(allow_self_upgrade=True)
    catalog = harness.client.get("/api/v1/game/levels").json()
    levels = catalog["levels"]
    assert len(levels) == 19  # spec 0051

    by_id = {lvl["id"]: lvl for lvl in levels}
    assert by_id["easy-1"]["tier"] == "free"
    assert by_id["easy-4"]["tier"] == "pro"
    assert by_id["medium-2"]["tier"] == "free"
    assert by_id["medium-3"]["tier"] == "pro"
    assert by_id["hard-1"]["tier"] == "pro"
    assert by_id["easy-1"]["order"] == 1
    assert by_id["easy-1"]["follow_up"] is not None
    assert "word_filter" in by_id["easy-4"]["constraints"]["disabled_checks"]
    credit_tool = next(
        t for t in by_id["medium-6"]["agent"]["tools"] if t["name"] == "issue_store_credit"
    )
    assert credit_tool["dual_use"] is True

    # Anonymous and free players can run free levels, but Pro levels return 403.
    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200
    assert (
        harness.client.post(
            "/api/v1/game/run", json={"level_id": "easy-1", "board": _board()}
        ).status_code
        == 200
    )
    for pro_id in ("easy-4", "medium-3", "hard-1"):
        res = harness.client.post("/api/v1/game/run", json={"level_id": pro_id, "board": _board()})
        assert res.status_code == 403

    _register(harness, "freeplayer@example.com")
    assert (
        harness.client.post(
            "/api/v1/game/run", json={"level_id": "medium-1", "board": _board()}
        ).status_code
        == 200
    )
    for pro_id in ("easy-4", "medium-3", "hard-1"):
        assert (
            harness.client.post(
                "/api/v1/game/run", json={"level_id": pro_id, "board": _board()}
            ).status_code
            == 403
        )
        assert harness.client.get(f"/api/v1/game/saves/{pro_id}").status_code == 403
        assert (
            harness.client.put(
                f"/api/v1/game/saves/{pro_id}",
                json={"board": _board(), "positions": {}},
            ).status_code
            == 403
        )

    # Upgrading to paid unlocks Pro levels for both running and saving.
    harness.container.game_agents = {
        "standard": ScriptedUsageChatModel(
            replies=[],
            default=ChatCompletion(
                text=json.dumps({"reply": "OK", "tool_calls": [], "refused": False}),
                input_tokens=20,
                output_tokens=10,
            ),
        ),
        "budget": ScriptedUsageChatModel(
            replies=[],
            default=ChatCompletion(
                text=json.dumps({"reply": "OK", "tool_calls": [], "refused": False}),
                input_tokens=20,
                output_tokens=10,
            ),
        ),
    }
    assert harness.client.post("/api/v1/auth/upgrade").status_code == 200
    assert (
        harness.client.post(
            "/api/v1/game/run", json={"level_id": "hard-1", "board": _board()}
        ).status_code
        == 200
    )
    assert (
        harness.client.put(
            "/api/v1/game/saves/hard-1",
            json={"board": _board(), "positions": {}},
        ).status_code
        == 200
    )
    assert harness.client.get("/api/v1/game/saves/hard-1").status_code == 200


@pytest.mark.spec("API-CAMP-002")
async def test_migration_purges_legacy_scores_and_preserves_mastered_stickily(
    tmp_path: Path, fake_supabase: Callable[..., FakeClient]
) -> None:
    assert SCORE_VERSION >= 3  # 4 since API-FAIR-006

    sql = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql"))).lower()
    assert "add column if not exists won" in sql
    assert "add column if not exists mastered" in sql
    assert "delete from game.scores where score_version < 3" in sql
    assert "delete from game.saved_boards where level_id in ('easy', 'medium', 'hard')" in sql

    # Sticky won & mastered across InMemory and Supabase score stores.
    stores = [
        InMemoryScoreStore(),
        SupabaseScoreStore(fake_supabase()),
    ]
    for store in stores:
        high_no_master = ScoreCreateRequest(
            player_name="Ada",
            level_id="easy-1",  # type: ignore[arg-type]
            total_score=9500,
            medal="gold",
            attacks_blocked=4,
            attacks_total=4,
            false_alarms=0,
            avg_latency_ms=1.0,
            total_cost_usd=0.0,
            board=BoardGraphSchema(nodes=[], edges=[]),
            won=True,  # type: ignore[call-arg]
            mastered=False,  # type: ignore[call-arg]
        )
        low_with_master = ScoreCreateRequest(
            player_name="Ada",
            level_id="easy-1",  # type: ignore[arg-type]
            total_score=8000,
            medal="silver",
            attacks_blocked=4,
            attacks_total=4,
            false_alarms=0,
            avg_latency_ms=5.0,
            total_cost_usd=0.0,
            board=BoardGraphSchema(nodes=[], edges=[]),
            won=True,  # type: ignore[call-arg]
            mastered=True,  # type: ignore[call-arg]
        )
        first = await store.record_score(high_no_master, email="ada@example.com")
        assert (first.total_score, first.won, first.mastered) == (9500, True, False)

        # Lower raw score that achieves mastery preserves best total_score AND sticks mastered=True.
        second = await store.record_score(low_with_master, email="ada@example.com")
        assert second.total_score == 9500
        assert second.won is True
        assert second.mastered is True

        # Higher score on medium-1 without mastery preserves previously sticky mastered=True too.
        med_master = ScoreCreateRequest(
            **{**low_with_master.model_dump(), "level_id": "medium-1", "total_score": 7000}
        )
        med_higher = ScoreCreateRequest(
            **{**high_no_master.model_dump(), "level_id": "medium-1", "total_score": 9800}
        )
        await store.record_score(med_master, email="ada@example.com")
        updated = await store.record_score(med_higher, email="ada@example.com")
        assert updated.total_score == 9800
        assert updated.won is True
        assert updated.mastered is True


@pytest.mark.spec("API-CAMP-003")
async def test_difficulty_leaderboard_aggregates_sum_per_category_and_progress_reports_all_levels(
    harness: Harness,
) -> None:
    # Anonymous progress starts zeroed for all 19 levels and 3 difficulty summaries.
    anon_prog = harness.client.get("/api/v1/game/progress")
    assert anon_prog.status_code == 200
    anon_body = anon_prog.json()
    assert len(anon_body["levels"]) == 19
    assert all(item["best_score"] == 0 and item["won"] is False for item in anon_body["levels"])
    assert [d["difficulty"] for d in anon_body["difficulties"]] == ["Easy", "Medium", "Hard"]

    def _mk(
        level_id: str, name: str, total: int, latency: float, cost: float, won: bool, mastered: bool
    ):
        return ScoreCreateRequest(
            player_name=name,
            level_id=level_id,  # type: ignore[arg-type]
            total_score=total,
            medal="gold"
            if total >= 8500
            else ("silver" if total >= 7000 else ("bronze" if won else "none")),
            attacks_blocked=4,
            attacks_total=4,
            false_alarms=0,
            avg_latency_ms=latency,
            total_cost_usd=cost,
            board=BoardGraphSchema(nodes=[], edges=[]),
            won=won,  # type: ignore[call-arg]
            mastered=mastered,  # type: ignore[call-arg]
        )

    await harness.scores.record_score(
        _mk("easy-1", "Ada", 9000, 1.0, 0.0, True, True), email="ada@example.com"
    )
    await harness.scores.record_score(
        _mk("easy-2", "Ada", 8800, 2.0, 0.0, True, False), email="ada@example.com"
    )
    await harness.scores.record_score(
        _mk("medium-1", "Ada", 8200, 300.0, 0.01, True, True), email="ada@example.com"
    )

    await harness.scores.record_score(
        _mk("easy-1", "Grace", 9200, 0.5, 0.0, True, False), email="grace@example.com"
    )
    await harness.scores.record_score(
        _mk("easy-1", "Alan", 9500, 0.5, 0.0, True, True), email="alan@example.com"
    )
    await harness.scores.record_score(
        _mk("easy-2", "Alan", 8300, 1.5, 0.0, True, False), email="alan@example.com"
    )

    easy_board = harness.client.get("/api/v1/game/leaderboard", params={"difficulty": "Easy"})
    assert easy_board.status_code == 200
    rows = easy_board.json()
    assert len(rows) == 3
    # Ada & Alan both tie at 17,800 (9000+8800 vs 9500+8300); stars, then the date, break it.
    assert rows[0]["total_score"] == 17800
    assert rows[1]["total_score"] == 17800
    assert {r["player_name"] for r in rows[:2]} == {"Ada", "Alan"}
    assert rows[0]["levels_total"] == 5
    assert rows[0]["max_possible_score"] == 50000
    assert rows[2]["player_name"] == "Grace"
    assert rows[2]["total_score"] == 9200
    assert rows[2]["levels_solved"] == 1
    assert rows[2]["levels_mastered"] == 0

    ada_row = next(r for r in rows if r["player_name"] == "Ada")
    assert ada_row["levels_solved"] == 2
    assert ada_row["levels_mastered"] == 1
    assert ada_row["avg_latency_ms"] == pytest.approx(1.5)

    all_board = harness.client.get("/api/v1/game/leaderboard")
    assert all_board.status_code == 200
    all_ada = next(r for r in all_board.json() if r["player_name"] == "Ada")
    assert all_ada["difficulty"] == "All"
    assert all_ada["total_score"] == 26000
    assert all_ada["levels_solved"] == 3
    assert all_ada["levels_mastered"] == 2
    assert all_ada["levels_total"] == 19

    # Register as Ada and verify GET /api/v1/game/progress reflects Ada's progress.
    _register(harness, "ada@example.com", "Ada")
    prog = harness.client.get("/api/v1/game/progress")
    assert prog.status_code == 200
    prog_data = prog.json()
    easy_summary = next(d for d in prog_data["difficulties"] if d["difficulty"] == "Easy")
    assert easy_summary["total_score"] == 17800
    assert easy_summary["levels_solved"] == 2
    assert easy_summary["levels_mastered"] == 1
    assert easy_summary["levels_total"] == 5
    easy_1_item = next(item for item in prog_data["levels"] if item["level_id"] == "easy-1")
    assert (easy_1_item["best_score"], easy_1_item["won"], easy_1_item["mastered"]) == (
        9000,
        True,
        True,
    )


def _scored(
    level_id: str, name: str, total: int, *, won: bool, latency: float = 1.0
) -> ScoreCreateRequest:
    return ScoreCreateRequest(
        player_name=name,
        level_id=level_id,  # type: ignore[arg-type]
        total_score=total,
        medal="gold" if won else "none",
        attacks_blocked=4,
        attacks_total=4,
        false_alarms=0,
        avg_latency_ms=latency,
        total_cost_usd=0.0,
        board=BoardGraphSchema(nodes=[], edges=[]),
        won=won,  # type: ignore[call-arg]
        mastered=False,  # type: ignore[call-arg]
    )


@pytest.mark.spec("API-CAMP-004")
async def test_leaderboard_sums_only_won_runs_and_hides_players_with_zero_points(
    harness: Harness,
) -> None:
    await harness.scores.record_score(
        _scored("easy-1", "Ada", 9000, won=True), email="ada@example.com"
    )
    await harness.scores.record_score(
        _scored("easy-2", "Ada", 6000, won=False), email="ada@example.com"
    )
    await harness.scores.record_score(
        _scored("easy-1", "Grace", 7000, won=False), email="grace@example.com"
    )
    await harness.scores.record_score(
        _scored("easy-1", "Alan", 0, won=True), email="alan@example.com"
    )

    rows = harness.client.get("/api/v1/game/leaderboard", params={"difficulty": "Easy"}).json()

    assert [(r["player_name"], r["total_score"]) for r in rows] == [("Ada", 9000)]


@pytest.mark.spec("API-CAMP-004")
async def test_a_lost_run_never_replaces_a_won_run_and_a_won_run_replaces_a_lost_one(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    stores = [
        InMemoryScoreStore(),
        SupabaseScoreStore(fake_supabase()),
    ]
    for store in stores:
        await store.record_score(_scored("easy-1", "Ada", 7000, won=True), email="a@x.com")
        kept = await store.record_score(_scored("easy-1", "Ada", 9500, won=False), email="a@x.com")
        assert (kept.total_score, kept.won) == (7000, True)

        await store.record_score(_scored("easy-2", "Ada", 9500, won=False), email="a@x.com")
        replaced = await store.record_score(
            _scored("easy-2", "Ada", 6000, won=True), email="a@x.com"
        )
        assert (replaced.total_score, replaced.won) == (6000, True)
