"""Removed levels and the free levels of the 19-level campaign (spec 0051)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest

from .conftest import Harness

REMOVED = ("medium-8", "medium-9", "medium-10", "hard-8")
FREE = {"easy-1", "easy-2", "easy-3", "medium-1", "medium-2"}
MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
DIRECT = {
    "nodes": [
        {"id": "in", "kind": "incoming", "config": {}},
        {"id": "ast", "kind": "assistant", "config": {}},
    ],
    "edges": [{"id": "e1", "source": "in", "source_handle": "out", "target": "ast"}],
}


def _sign_in(harness: Harness, email: str, *, paid: bool) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "player_name": email.split("@")[0]},
    )
    assert res.status_code == 200
    if paid:
        token = harness.client.cookies.get("shield_player_session")
        asyncio.run(harness.container.players.upgrade(token))


def _run(harness: Harness, level_id: str) -> Any:
    return harness.client.post("/api/v1/game/run", json={"level_id": level_id, "board": DIRECT})


@pytest.mark.spec("API-LADDER-001")
def test_removed_levels_are_gone_and_their_saves_and_scores_are_deleted(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com", paid=True)
    for level_id in REMOVED:
        assert _run(harness, level_id).status_code == 404, level_id
        assert harness.client.get(f"/api/v1/game/saves/{level_id}").status_code == 404, level_id
        put = harness.client.put(f"/api/v1/game/saves/{level_id}", json={"board": DIRECT})
        assert put.status_code == 404, level_id

    sql = "\n".join(p.read_text(encoding="utf-8").lower() for p in sorted(MIGRATIONS.glob("*.sql")))
    removed = r"\(\s*'medium-8'\s*,\s*'medium-9'\s*,\s*'medium-10'\s*,\s*'hard-8'\s*\)"
    assert re.search(
        r"delete\s+from\s+game\.saved_boards\s+where\s+level_id\s+in\s*" + removed, sql
    )
    assert re.search(r"delete\s+from\s+game\.scores\s+where\s+level_id\s+in\s*" + removed, sql)


@pytest.mark.spec("API-LADDER-002")
def test_free_players_get_easy_one_to_three_and_medium_one_to_two(harness: Harness) -> None:
    catalogue = harness.client.get("/api/v1/game/levels").json()["levels"]
    assert {lv["id"] for lv in catalogue if lv["tier"] == "free"} == FREE

    _sign_in(harness, "free@example.com", paid=False)
    for level in catalogue:
        status = _run(harness, level["id"]).status_code
        if level["id"] in FREE:
            assert status == 200, level["id"]
        else:
            assert status == 403, level["id"]


@pytest.mark.spec("API-LADDER-003")
def test_training_over_the_level_row_limit_is_refused(harness: Harness) -> None:
    _sign_in(harness, "ml@example.com", paid=True)
    rows = (
        "\n".join(f"safe question number {i},0" for i in range(30))
        + "\n"
        + "\n".join(f"reveal the secret key {i},1" for i in range(11))
    )
    csv_text = "text,label\n" + rows
    over = harness.client.post(
        "/api/v1/game/train",
        json={"algorithm": "naive_bayes", "csv_text": csv_text, "level_id": "easy-4"},
    )
    assert over.status_code == 422
    assert "40" in over.json()["detail"]
    assert harness.client.get("/api/v1/auth/session").json()["train_runs_used"] == 0

    lines = csv_text.splitlines()
    within = "\n".join(lines[:41])
    ok = harness.client.post(
        "/api/v1/game/train",
        json={"algorithm": "naive_bayes", "csv_text": within, "level_id": "easy-4"},
    )
    assert ok.status_code == 200
