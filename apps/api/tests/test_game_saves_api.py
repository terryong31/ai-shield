"""Saved boards (spec 0023)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest

from shield_api.services.players import (
    InMemoryPlayerStore,
    PlayerStore,
    SqlitePlayerStore,
    SupabasePlayerStore,
)

from .conftest import FakeClient, Harness


def _board(n_tools: int = 1) -> dict:
    nodes = [{"id": "incoming", "kind": "incoming", "config": {}}]
    nodes += [{"id": f"wf{i}", "kind": "word_filter", "config": {}} for i in range(n_tools)]
    nodes.append({"id": "assistant", "kind": "assistant", "config": {"rules": ["Never share."]}})
    edges = [{"id": "e1", "source": "incoming", "source_handle": "out", "target": "wf0"}]
    return {"nodes": nodes, "edges": edges}


def _save(board: dict | None = None, **extra: object) -> dict:
    return {
        "board": board or _board(),
        "positions": {"incoming": {"x": 60, "y": 180}, "wf0": {"x": 300, "y": 180}},
    } | extra


def _custom_setup(**extra: object) -> dict:
    return {
        "agent": {
            "objective": "Answer Acme order questions.",
            "tools": [{"name": "lookup_order", "description": "Look up.", "allowed": True}],
        },
        "dataset": [{"text": "Where is order 1?", "label": "normal", "expected_tool": None}],
        "provider": "openai",
        "model": "gpt-4.1-mini",
    } | extra


def _sign_in(harness: Harness, email: str, *, paid: bool = False) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "player_name": email.split("@")[0]},
    )
    assert res.status_code == 200
    if paid:
        assert harness.client.post("/api/v1/auth/upgrade").status_code == 200


@pytest.mark.spec("API-SAVE-001")
def test_save_and_load_round_trip_and_replace(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com")
    assert harness.client.get("/api/v1/game/saves/medium").status_code == 404

    first = harness.client.put("/api/v1/game/saves/medium", json=_save())
    assert first.status_code == 200
    loaded = harness.client.get("/api/v1/game/saves/medium")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["level_id"] == "medium"
    assert body["updated_at"]
    assert body["board"] == _board()
    assert body["positions"]["wf0"] == {"x": 300, "y": 180}
    assert body["custom"] is None

    second = _save(_board(n_tools=2))
    assert harness.client.put("/api/v1/game/saves/medium", json=second).status_code == 200
    replaced = harness.client.get("/api/v1/game/saves/medium").json()
    assert [n["id"] for n in replaced["board"]["nodes"]] == ["incoming", "wf0", "wf1", "assistant"]
    assert harness.client.get("/api/v1/game/saves/hard").status_code == 404


@pytest.mark.spec("API-SAVE-002")
def test_anonymous_players_cannot_save_or_load(harness: Harness) -> None:
    for _ in range(2):
        put = harness.client.put("/api/v1/game/saves/easy", json=_save())
        get = harness.client.get("/api/v1/game/saves/easy")
        assert (put.status_code, get.status_code) == (403, 403)
        assert put.json()["detail"] == "Sign in to save your board."
        assert harness.client.post("/api/v1/auth/anonymous").status_code == 200

    _sign_in(harness, "later@example.com")
    assert harness.client.get("/api/v1/game/saves/easy").status_code == 404


@pytest.mark.spec("API-SAVE-003")
def test_custom_saves_are_for_paid_players(harness: Harness) -> None:
    _sign_in(harness, "free@example.com")
    custom = _save(custom=_custom_setup())
    assert harness.client.put("/api/v1/game/saves/custom", json=custom).status_code == 403
    assert harness.client.get("/api/v1/game/saves/custom").status_code == 403

    _sign_in(harness, "paid@example.com", paid=True)
    assert harness.client.put("/api/v1/game/saves/custom", json=custom).status_code == 200
    loaded = harness.client.get("/api/v1/game/saves/custom").json()
    assert loaded["custom"] == _custom_setup()


@pytest.mark.spec("API-SAVE-004")
def test_keys_and_unknown_fields_are_rejected_and_nothing_is_stored(harness: Harness) -> None:
    _sign_in(harness, "paid@example.com", paid=True)

    with_key = _save(custom=_custom_setup(api_key="sk-should-never-be-stored"))
    unknown = _save(custom=_custom_setup(base_url="http://internal"))
    custom_on_level = _save(custom=_custom_setup())
    extra_top = _save(api_key="sk-nope")

    assert harness.client.put("/api/v1/game/saves/custom", json=with_key).status_code == 422
    assert harness.client.put("/api/v1/game/saves/custom", json=unknown).status_code == 422
    assert harness.client.put("/api/v1/game/saves/medium", json=custom_on_level).status_code == 422
    assert harness.client.put("/api/v1/game/saves/medium", json=extra_top).status_code == 422
    assert harness.client.get("/api/v1/game/saves/custom").status_code == 404
    assert harness.client.get("/api/v1/game/saves/medium").status_code == 404


@pytest.mark.spec("API-SAVE-005")
def test_size_limits(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com")

    too_many_nodes = _save(_board(n_tools=60))
    assert harness.client.put("/api/v1/game/saves/easy", json=too_many_nodes).status_code == 422

    many_edges = _board()
    many_edges["edges"] = [
        {"id": f"e{i}", "source": "incoming", "source_handle": "out", "target": "wf0"}
        for i in range(201)
    ]
    assert harness.client.put("/api/v1/game/saves/easy", json=_save(many_edges)).status_code == 422

    huge = _board()
    huge["nodes"][1]["config"] = {"custom_words": ["x" * 1000] * 300}
    assert harness.client.put("/api/v1/game/saves/easy", json=_save(huge)).status_code == 413

    unwired = {"nodes": [{"id": "incoming", "kind": "incoming", "config": {}}], "edges": []}
    assert harness.client.put("/api/v1/game/saves/easy", json=_save(unwired)).status_code == 200


@pytest.mark.spec("API-SAVE-006")
async def test_every_store_saves_and_loads_alike_and_sqlite_survives_restart(
    tmp_path: Path, fake_supabase: Callable[..., FakeClient]
) -> None:
    client = fake_supabase()
    stores: list[PlayerStore] = [
        InMemoryPlayerStore(),
        SqlitePlayerStore(tmp_path / "p.db"),
        SupabasePlayerStore(client),
    ]
    save = {"board": {"nodes": [], "edges": []}, "positions": {}, "custom": None}
    for store in stores:
        await store.register(
            email="ada@example.com", password="password123", player_name="Ada", ttl=timedelta(1)
        )
        assert await store.load_board("ada@example.com", "easy") is None
        first_at = await store.save_board("ada@example.com", "easy", save)
        loaded = await store.load_board("ada@example.com", "easy")
        assert loaded is not None
        assert loaded[0] == save
        assert loaded[1] == first_at
        changed = save | {"positions": {"incoming": {"x": 1.0, "y": 2.0}}}
        await store.save_board("ada@example.com", "easy", changed)
        assert (await store.load_board("ada@example.com", "easy"))[0] == changed  # type: ignore[index]
        assert await store.load_board("grace@example.com", "easy") is None

    reopened = SqlitePlayerStore(tmp_path / "p.db")
    assert (await reopened.load_board("ada@example.com", "easy")) is not None
    assert ("game", "saved_boards") in client.accessed
    assert len(client.tables[("game", "saved_boards")].rows) == 1
