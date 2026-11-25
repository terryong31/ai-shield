"""Saved boards (spec 0023)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest

from shield_api.services.players import (
    InMemoryPlayerStore,
    PlayerStore,
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
            "tools": [
                {
                    "name": "lookup_order",
                    "description": "Look up.",
                    "allowed": True,
                    "dual_use": False,
                }
            ],
        },
        "dataset": [{"text": "Where is order 1?", "label": "normal", "expected_tool": None}],
        "provider": "openai",
        "model": "gpt-4.1-mini",
    } | extra


def _sign_in(harness: Harness, email: str, *, paid: bool = False) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "player_name": email.split("@")[0]},
    )
    assert res.status_code == 200
    if paid:
        import asyncio

        token = harness.client.cookies.get("shield_player_session")
        asyncio.run(harness.container.players.upgrade(token))


@pytest.mark.spec("API-SAVE-001")
def test_save_and_load_round_trip_and_replace(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com")
    assert harness.client.get("/api/v1/game/saves/medium-1").status_code == 404

    first = harness.client.put("/api/v1/game/saves/medium-1", json=_save())
    assert first.status_code == 200
    loaded = harness.client.get("/api/v1/game/saves/medium-1")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["level_id"] == "medium-1"
    assert body["updated_at"]
    assert body["board"] == _board()
    assert body["positions"]["wf0"] == {"x": 300, "y": 180}
    assert body["custom"] is None

    second = _save(_board(n_tools=2))
    assert harness.client.put("/api/v1/game/saves/medium-1", json=second).status_code == 200
    replaced = harness.client.get("/api/v1/game/saves/medium-1").json()
    assert [n["id"] for n in replaced["board"]["nodes"]] == ["incoming", "wf0", "wf1", "assistant"]
    assert harness.client.get("/api/v1/game/saves/easy-1").status_code == 404


@pytest.mark.spec("API-SAVE-002")
def test_anonymous_players_cannot_save_or_load(harness: Harness) -> None:
    for _ in range(2):
        put = harness.client.put("/api/v1/game/saves/easy-1", json=_save())
        get = harness.client.get("/api/v1/game/saves/easy-1")
        assert (put.status_code, get.status_code) == (403, 403)
        assert put.json()["detail"] == "Sign in to save your board."
        assert harness.client.post("/api/v1/auth/anonymous").status_code == 200

    _sign_in(harness, "later@example.com")
    assert harness.client.get("/api/v1/game/saves/easy-1").status_code == 404


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
    assert (
        harness.client.put("/api/v1/game/saves/medium-1", json=custom_on_level).status_code == 422
    )
    assert harness.client.put("/api/v1/game/saves/medium-1", json=extra_top).status_code == 422
    assert harness.client.get("/api/v1/game/saves/custom").status_code == 404
    assert harness.client.get("/api/v1/game/saves/medium-1").status_code == 404


@pytest.mark.spec("API-SAVE-005")
def test_size_limits(harness: Harness) -> None:
    _sign_in(harness, "ada@example.com")

    too_many_nodes = _save(_board(n_tools=60))
    assert harness.client.put("/api/v1/game/saves/easy-1", json=too_many_nodes).status_code == 422

    many_edges = _board()
    many_edges["edges"] = [
        {"id": f"e{i}", "source": "incoming", "source_handle": "out", "target": "wf0"}
        for i in range(201)
    ]
    assert (
        harness.client.put("/api/v1/game/saves/easy-1", json=_save(many_edges)).status_code == 422
    )

    huge = _board()
    huge["nodes"][1]["config"] = {"custom_words": ["x" * 1000] * 300}
    assert harness.client.put("/api/v1/game/saves/easy-1", json=_save(huge)).status_code == 413

    unwired = {"nodes": [{"id": "incoming", "kind": "incoming", "config": {}}], "edges": []}
    assert harness.client.put("/api/v1/game/saves/easy-1", json=_save(unwired)).status_code == 200


@pytest.mark.spec("API-SAVE-006")
async def test_every_store_saves_and_loads_alike(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    client = fake_supabase()
    stores: list[PlayerStore] = [
        InMemoryPlayerStore(),
        SupabasePlayerStore(client),
    ]
    save = {"board": {"nodes": [], "edges": []}, "positions": {}, "custom": None}
    for store in stores:
        await store.sign_in_verified(email="ada@example.com", player_name="Ada", ttl=timedelta(1))
        assert await store.load_board("ada@example.com", "easy-1") is None
        first_at = await store.save_board("ada@example.com", "easy-1", save)
        loaded = await store.load_board("ada@example.com", "easy-1")
        assert loaded is not None
        assert loaded[0] == save
        assert loaded[1] == first_at
        changed = save | {"positions": {"incoming": {"x": 1.0, "y": 2.0}}}
        await store.save_board("ada@example.com", "easy-1", changed)
        assert (await store.load_board("ada@example.com", "easy-1"))[0] == changed  # type: ignore[index]
        assert await store.load_board("grace@example.com", "easy-1") is None

    assert ("game", "saved_boards") in client.accessed
    assert len(client.tables[("game", "saved_boards")].rows) == 1


@pytest.mark.spec("API-SAVE-007")
def test_browser_preflight_allows_saving_a_board(harness: Harness) -> None:
    preflight = {
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "content-type",
    }

    allowed = harness.client.options(
        "/api/v1/game/saves/easy-1", headers={"Origin": "http://localhost:3000", **preflight}
    )
    foreign = harness.client.options(
        "/api/v1/game/saves/easy-1", headers={"Origin": "https://evil.example", **preflight}
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "PUT" in allowed.headers["access-control-allow-methods"]
    assert "access-control-allow-origin" not in foreign.headers


@pytest.mark.spec("API-ML-001")
async def test_get_saved_board_migrates_legacy_quick_screen_to_ml_classifier(
    harness: Harness,
) -> None:
    _sign_in(harness, "legacy@example.com")
    legacy_save = {
        "board": {
            "nodes": [
                {"id": "incoming", "kind": "incoming", "config": {}},
                {
                    "id": "qs",
                    "kind": "quick_screen",
                    "config": {"safe_threshold": 0.25, "block_threshold": 0.8},
                },
                {"id": "assistant", "kind": "assistant", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "incoming", "source_handle": "out", "target": "qs"},
                {"id": "e2", "source": "qs", "source_handle": "safe", "target": "assistant"},
                {"id": "e3", "source": "qs", "source_handle": "suspicious", "target": "assistant"},
            ],
        },
        "positions": {"incoming": {"x": 60, "y": 180}, "qs": {"x": 300, "y": 180}},
        "custom": None,
    }
    await harness.container.players.save_board("legacy@example.com", "medium-1", legacy_save)

    loaded = harness.client.get("/api/v1/game/saves/medium-1")
    assert loaded.status_code == 200
    body = loaded.json()
    qs_node = next(n for n in body["board"]["nodes"] if n["id"] == "qs")
    assert qs_node["kind"] == "ml_classifier"
    assert qs_node["config"] == {
        "algorithm": "tfidf",
        "safe_threshold": 0.25,
        "block_threshold": 0.8,
    }
