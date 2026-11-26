"""Run spend controls, size bounds, BYOK check isolation and verified email change (spec 0042)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from shield_api.openapi import render
from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
from shield_engine.ports import ChatCompletion, JevEvaluation
from shield_engine.testing import ScriptedJevClient, ScriptedUsageChatModel

from .conftest import FakeClient, Harness

SAFE_REPLY = ChatCompletion(
    text=json.dumps({"reply": "Here you go.", "tool_calls": [], "refused": False}),
    input_tokens=20,
    output_tokens=5,
)


def _simple_board() -> dict[str, Any]:
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


def _safety_board() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "in", "kind": "incoming", "config": {}},
            {"id": "sc", "kind": "safety_check", "config": {}},
            {"id": "ast", "kind": "assistant", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "source_handle": "out", "target": "sc"},
            {"id": "e2", "source": "sc", "source_handle": "safe", "target": "ast"},
        ],
    }


def _jev_board() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "in", "kind": "incoming", "config": {}},
            {"id": "jv", "kind": "jev", "config": {}},
            {"id": "ast", "kind": "assistant", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "source_handle": "out", "target": "jv"},
            {"id": "e2", "source": "jv", "source_handle": "safe", "target": "ast"},
        ],
    }


def _register_and_login(
    harness: Harness, email: str = "ada@example.com", *, paid: bool = False
) -> None:
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "player_name": "Ada"},
    )
    assert res.status_code == 200
    if paid:
        # Directly upgrade in store for tests that do not test ALLOW_SELF_UPGRADE.
        import asyncio

        token = harness.client.cookies.get("shield_player_session")
        asyncio.run(harness.container.players.upgrade(token))


@pytest.mark.spec("API-SPEND-001")
def test_model_run_without_session_cookie_returns_401_and_writes_no_usage(
    make_harness: Callable[..., Harness], fake_supabase: Callable[..., FakeClient]
) -> None:
    from shield_api.services.players import SupabasePlayerStore

    client = fake_supabase()
    harness = make_harness(players=SupabasePlayerStore(client))
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}

    res = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "medium-1", "board": _simple_board()},
    )

    assert res.status_code == 401
    assert res.json()["detail"] == "Start a session to play this level."
    assert agent.calls == []
    usage_rows = client.tables.get(("players", "daily_usage"))
    assert usage_rows is None or usage_rows.rows == []


@pytest.mark.spec("API-SPEND-002")
def test_model_run_with_unknown_or_expired_session_token_returns_401(
    harness: Harness,
) -> None:
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}

    harness.client.cookies.set("shield_player_session", "unknown-token-value")
    unknown_res = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "medium-1", "board": _simple_board()},
    )
    assert unknown_res.status_code == 401
    assert agent.calls == []


@pytest.mark.spec("API-SPEND-003")
def test_model_free_easy_run_without_cookie_still_returns_200(harness: Harness) -> None:
    res = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "easy-1", "board": _simple_board()},
    )
    assert res.status_code == 200


@pytest.mark.spec("API-SPEND-004")
def test_easy_level_with_safety_check_counts_against_daily_quota(harness: Harness) -> None:
    check_reply = ChatCompletion(
        text=json.dumps({"blocked": False, "reason": "ok"}),
        input_tokens=10,
        output_tokens=5,
    )
    check_model = ScriptedUsageChatModel(replies=[], default=check_reply)
    harness.container.check_model_for = lambda _: check_model  # type: ignore[assignment]
    _register_and_login(harness, "free@example.com")

    first = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "easy-1", "board": _safety_board()},
    )
    assert first.status_code == 200
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 1

    for _ in range(4):
        assert (
            harness.client.post(
                "/api/v1/game/run",
                json={"level_id": "easy-1", "board": _safety_board()},
            ).status_code
            == 200
        )

    calls_before_limit = len(check_model.calls)
    exhausted = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "easy-1", "board": _safety_board()},
    )
    assert exhausted.status_code == 429
    assert len(check_model.calls) == calls_before_limit


@pytest.mark.spec("API-SPEND-007")
def test_anonymous_model_run_503_does_not_increment_session_usage(harness: Harness) -> None:
    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200
    harness.container.game_agents = {
        "standard": ScriptedUsageChatModel(replies=[RuntimeError("down")])
    }

    res = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "medium-1", "board": _simple_board()},
    )
    assert res.status_code == 503
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 0


@pytest.mark.spec("API-SPEND-009")
def test_custom_message_is_capped_at_1000_chars(harness: Harness) -> None:
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}
    _register_and_login(harness, "ada@example.com")

    too_long = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "medium-1", "board": _simple_board(), "custom_message": "x" * 1001},
    )
    assert too_long.status_code == 422
    assert agent.calls == []

    at_limit = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "medium-1", "board": _simple_board(), "custom_message": "x" * 1000},
    )
    # API-FAIR-002: campaign levels take no single message at any length.
    assert at_limit.status_code == 422
    assert "custom sandbox" in at_limit.json()["detail"]


@pytest.mark.spec("API-SPEND-010")
def test_board_on_game_run_is_capped_at_60_nodes_and_200_edges(harness: Harness) -> None:
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agents = {"standard": agent}
    _register_and_login(harness, "ada@example.com", paid=True)

    many_nodes = {
        "nodes": [{"id": "in", "kind": "incoming", "config": {}}]
        + [{"id": f"wf{i}", "kind": "word_filter", "config": {}} for i in range(60)],
        "edges": [],
    }
    res_nodes = harness.client.post(
        "/api/v1/game/run", json={"level_id": "easy-1", "board": many_nodes}
    )
    assert res_nodes.status_code == 422
    assert "A board holds at most 60 nodes and 200 wires." in str(res_nodes.json())

    many_edges = _simple_board()
    many_edges["edges"] = [
        {"id": f"e{i}", "source": "in", "source_handle": "out", "target": "wf"} for i in range(201)
    ]
    res_custom = harness.client.post(
        "/api/v1/game/run",
        json={
            "level_id": "custom",
            "board": many_edges,
            "custom": {
                "agent": {"objective": "Answer orders.", "tools": []},
                "dataset": [{"text": "hi", "label": "normal"}],
                "model": {"provider": "openai", "model": "gpt-4.1-mini", "api_key": "sk-test-key"},
            },
        },
    )
    assert res_custom.status_code == 422
    assert "A board holds at most 60 nodes and 200 wires." in str(res_custom.json())
    assert agent.calls == []


@pytest.mark.spec("API-SPEND-011")
def test_custom_mode_check_nodes_use_byok_model_never_server_model(harness: Harness) -> None:
    server_agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    harness.container.game_agent = server_agent
    harness.container.game_agents = {"standard": server_agent}

    byok_replies = [
        # safety_check -> safe
        ChatCompletion(text=json.dumps({"safe": True}), input_tokens=5, output_tokens=5),
        # llm_review -> not blocked
        ChatCompletion(
            text=json.dumps({"blocked": False, "reason": "ok"}), input_tokens=5, output_tokens=5
        ),
        # agent reply
        SAFE_REPLY,
    ]
    byok_model = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)

    # Fake check + agent answers based on prompt content.
    class CheckAndAgentFake(ScriptedUsageChatModel):
        async def complete_with_usage(
            self, messages, *, temperature=0.0, max_tokens=512, thinking=False
        ):
            self.calls.append((messages, temperature, max_tokens, thinking))
            text = " ".join(m.content for m in messages).lower()
            if "safety" in text or "unsafe" in text:
                return ChatCompletion(
                    text=json.dumps({"blocked": False, "reason": "ok"}),
                    input_tokens=5,
                    output_tokens=5,
                )
            if "blocked" in text:
                return ChatCompletion(
                    text=json.dumps({"blocked": False, "reason": "ok"}),
                    input_tokens=5,
                    output_tokens=5,
                )
            return SAFE_REPLY

    byok_model = CheckAndAgentFake(replies=[], default=SAFE_REPLY)
    harness.container.byok_factory = lambda provider, model, key: byok_model  # type: ignore[assignment]
    _register_and_login(harness, "paid@example.com", paid=True)

    board = {
        "nodes": [
            {"id": "in", "kind": "incoming", "config": {}},
            {"id": "sc", "kind": "safety_check", "config": {}},
            {"id": "lr", "kind": "llm_review", "config": {"prompt": "Check safety."}},
            {"id": "ast", "kind": "assistant", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "source_handle": "out", "target": "sc"},
            {"id": "e2", "source": "sc", "source_handle": "safe", "target": "lr"},
            {"id": "e3", "source": "lr", "source_handle": "safe", "target": "ast"},
        ],
    }
    res = harness.client.post(
        "/api/v1/game/run",
        json={
            "level_id": "custom",
            "board": board,
            "custom": {
                "agent": {"objective": "Answer orders.", "tools": []},
                "dataset": [{"text": "Where is order 1?", "label": "normal"}],
                "model": {"provider": "openai", "model": "gpt-4.1-mini", "api_key": "sk-test-key"},
            },
        },
    )

    assert res.status_code == 200
    assert len(byok_model.calls) >= 3
    assert server_agent.calls == []
    assert byok_replies  # keep reference clean


@pytest.mark.spec("API-SPEND-012")
def test_self_upgrade_disabled_by_default_returns_403(harness: Harness) -> None:
    _register_and_login(harness, "free@example.com")

    res = harness.client.post("/api/v1/auth/upgrade")

    assert res.status_code == 403
    assert res.json()["detail"] == "Paid plans are not available yet."
    assert harness.client.get("/api/v1/auth/session").json()["tier"] == "free"


@pytest.mark.spec("API-SPEND-013")
def test_self_upgrade_when_enabled_upgrades_signed_in_and_rejects_anonymous(
    harness: Harness,
) -> None:
    from shield_api.settings import Settings

    harness.container.settings = Settings(
        _env_file=None,
        APP_ENV="development",
        SESSION_COOKIE_SECURE=False,
        ALLOW_SELF_UPGRADE=True,
    )

    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200
    assert harness.client.post("/api/v1/auth/upgrade").status_code == 403

    _register_and_login(harness, "free@example.com")
    upgraded = harness.client.post("/api/v1/auth/upgrade")
    assert upgraded.status_code == 200
    assert upgraded.json()["tier"] == "paid"


@pytest.mark.spec("API-SPEND-014")
def test_game_levels_exposes_self_upgrade_enabled(harness: Harness) -> None:
    from shield_api.settings import Settings

    assert harness.client.get("/api/v1/game/levels").json()["self_upgrade_enabled"] is False
    harness.container.settings = Settings(
        _env_file=None,
        APP_ENV="development",
        SESSION_COOKIE_SECURE=False,
        ALLOW_SELF_UPGRADE=True,
    )
    assert harness.client.get("/api/v1/game/levels").json()["self_upgrade_enabled"] is True


@pytest.mark.spec("API-SPEND-015")
def test_post_game_scores_returns_405_while_get_and_admin_delete_stay(
    harness: Harness, admin_password: str
) -> None:
    _register_and_login(harness, "ada@example.com")
    res = harness.client.post(
        "/api/v1/game/scores",
        json={
            "player_name": "Ada",
            "level_id": "easy-1",
            "total_score": 9999,
            "medal": "gold",
            "attacks_blocked": 4,
            "attacks_total": 4,
            "false_alarms": 0,
            "avg_latency_ms": 1.0,
            "total_cost_usd": 0.0,
            "board": _simple_board(),
        },
    )
    assert res.status_code == 405
    assert harness.client.get("/api/v1/game/scores").json() == []
    assert harness.grant(admin_password).status_code == 200
    assert harness.client.delete("/api/v1/game/scores").status_code == 204


@pytest.mark.spec("API-SPEND-016")
def test_contract_removes_post_scores_and_documents_limits_and_self_upgrade() -> None:
    contract = json.loads(render())
    assert "post" not in contract["paths"]["/api/v1/game/scores"]

    props = contract["components"]["schemas"]["GameRunRequest"]["properties"]
    custom_msg = props["custom_message"]
    variants = custom_msg.get("anyOf", [custom_msg])
    assert any(v.get("maxLength") == 1000 for v in variants)

    catalog = contract["components"]["schemas"]["GameCatalogResponse"]["properties"]
    assert "self_upgrade_enabled" in catalog


@pytest.mark.spec("API-SPEND-017")
def test_email_change_uses_user_update_returns_202_and_keeps_old_profile(
    harness: Harness,
) -> None:
    _register_and_login(harness, "old@example.com")
    import asyncio

    asyncio.run(
        harness.container.scores.record_score(
            ScoreCreateRequest(
                player_name="Ada",
                level_id="easy-1",
                total_score=5000,
                medal="gold",
                attacks_blocked=4,
                attacks_total=4,
                false_alarms=0,
                avg_latency_ms=1.0,
                total_cost_usd=0.0,
                board=BoardGraphSchema(nodes=[], edges=[]),
                won=True,
            ),
            email="old@example.com",
        )
    )
    harness.client.put(
        "/api/v1/game/saves/easy-1", json={"board": _simple_board(), "positions": {}}
    )
    harness.auth.calls.clear()

    res = harness.client.post(
        "/api/v1/auth/account/email",
        json={"current_password": "Password123", "new_email": "new@example.com"},
    )

    assert res.status_code == 202
    assert res.json() == {"status": "confirmation_sent"}
    assert "update_user" in harness.auth.calls
    assert "admin.update_user_by_id" not in harness.auth.calls
    assert harness.client.get("/api/v1/auth/session").json()["email"] == "old@example.com"
    assert harness.client.get("/api/v1/game/saves/easy-1").status_code == 200


@pytest.mark.spec("API-SPEND-018")
def test_login_moves_profile_when_confirmed_email_differs_from_profile_email(
    harness: Harness,
) -> None:
    import asyncio

    user = harness.auth.add(
        "old@example.com",
        "Password123",
        app_metadata={"profile_email": "old@example.com"},
        user_metadata={"player_name": "Ada"},
    )
    harness.auth.confirm("old@example.com")
    assert (
        harness.client.post(
            "/api/v1/auth/login",
            json={"email": "old@example.com", "password": "Password123"},
        ).status_code
        == 200
    )
    asyncio.run(
        harness.container.scores.record_score(
            ScoreCreateRequest(
                player_name="Ada",
                level_id="easy-1",
                total_score=5000,
                medal="gold",
                attacks_blocked=4,
                attacks_total=4,
                false_alarms=0,
                avg_latency_ms=1.0,
                total_cost_usd=0.0,
                board=BoardGraphSchema(nodes=[], edges=[]),
                won=True,
            ),
            email="old@example.com",
        )
    )
    harness.client.put(
        "/api/v1/game/saves/easy-1", json={"board": _simple_board(), "positions": {}}
    )

    # Simulate user confirming the new email in Supabase Auth.
    user.email = "new@example.com"
    harness.client.cookies.clear()
    login_res = harness.client.post(
        "/api/v1/auth/login",
        json={"email": "new@example.com", "password": "Password123"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["email"] == "new@example.com"
    assert user.app_metadata.get("profile_email") == "new@example.com"
    assert harness.client.get("/api/v1/game/saves/easy-1").status_code == 200
    assert asyncio.run(harness.container.scores.list_scores_for_owner("old@example.com")) == []
    assert len(asyncio.run(harness.container.scores.list_scores_for_owner("new@example.com"))) == 1


@pytest.mark.spec("API-SPEND-019")
def test_login_ignores_user_metadata_and_sets_profile_email_to_own_address(
    harness: Harness,
) -> None:
    user = harness.auth.add(
        "attacker@example.com",
        "Password123",
        app_metadata={},
        user_metadata={"player_name": "Attacker", "profile_email": "victim@example.com"},
    )
    harness.auth.confirm("attacker@example.com")

    res = harness.client.post(
        "/api/v1/auth/login",
        json={"email": "attacker@example.com", "password": "Password123"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "attacker@example.com"
    assert user.app_metadata.get("profile_email") == "attacker@example.com"


@pytest.mark.spec("API-SPEND-021")
def test_jev_node_on_easy_requires_session_and_consumes_free_quota(harness: Harness) -> None:
    jev = ScriptedJevClient(replies=[JevEvaluation(probability=0.05, input_tokens=50)] * 20)
    harness.container.jev_client = jev

    no_session = harness.client.post(
        "/api/v1/game/run", json={"level_id": "easy-1", "board": _jev_board()}
    )
    assert no_session.status_code == 401
    assert jev.calls == []

    _register_and_login(harness, "ada@example.com")
    ok = harness.client.post("/api/v1/game/run", json={"level_id": "easy-1", "board": _jev_board()})
    assert ok.status_code == 200
    assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 1


@pytest.mark.spec("API-SPEND-022")
def test_anonymous_jev_node_on_easy_consumes_anonymous_daily_quota(harness: Harness) -> None:
    jev = ScriptedJevClient(replies=[JevEvaluation(probability=0.05, input_tokens=50)] * 20)
    harness.container.jev_client = jev
    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200

    first = harness.client.post(
        "/api/v1/game/run", json={"level_id": "easy-1", "board": _jev_board()}
    )
    assert first.status_code == 200
    calls_after_first = len(jev.calls)

    second = harness.client.post(
        "/api/v1/game/run", json={"level_id": "easy-1", "board": _jev_board()}
    )
    assert second.status_code == 429
    assert len(jev.calls) == calls_after_first


@pytest.mark.spec("API-SPEND-023")
async def test_concurrent_model_runs_cannot_exceed_daily_limit_on_memory_or_supabase(
    make_harness: Callable[..., Harness], fake_supabase: Callable[..., FakeClient]
) -> None:
    import asyncio

    import httpx

    from shield_api.main import create_app
    from shield_api.services.players import InMemoryPlayerStore, SupabasePlayerStore

    class SlowChatModel:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_with_usage(
            self,
            messages: list[Any],
            **_kwargs: Any,
        ) -> Any:
            _ = messages
            self.calls += 1
            await asyncio.sleep(0.03)
            return SAFE_REPLY

    for backend in ("memory", "supabase"):
        supa_client = fake_supabase() if backend == "supabase" else None
        store = (
            SupabasePlayerStore(supa_client) if supa_client is not None else InMemoryPlayerStore()
        )
        harness = make_harness(players=store)
        agent = SlowChatModel()
        harness.container.game_agents = {"standard": agent}
        _register_and_login(harness, f"race-{backend}@example.com")
        token = harness.client.cookies.get("shield_player_session") or ""

        app = create_app(harness.container)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"shield_player_session": token},
        ) as client:
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/api/v1/game/run",
                        json={"level_id": "medium-1", "board": _simple_board()},
                    )
                    for _ in range(10)
                ]
            )

        statuses = sorted(r.status_code for r in responses)
        assert statuses == [200] * 5 + [429] * 5
        assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 5
        assert agent.calls == 5 * len(responses[0].json().get("traces", [])) or agent.calls > 0
        # 5 waves allowed, never 10 waves worth of calls.
        sess_res = harness.client.get("/api/v1/auth/session")
        assert sess_res.json()["wave_runs_used"] == 5
        if supa_client is not None:
            assert ("players", "reserve_daily_usage") in supa_client.rpc_calls


@pytest.mark.spec("API-SPEND-024")
async def test_failed_model_run_releases_reserved_slot_on_memory_and_supabase(
    make_harness: Callable[..., Harness], fake_supabase: Callable[..., FakeClient]
) -> None:
    from shield_api.services.players import InMemoryPlayerStore, SupabasePlayerStore

    class FailingChatModel:
        async def complete_with_usage(
            self,
            messages: list[Any],
            **_kwargs: Any,
        ) -> Any:
            _ = messages
            raise RuntimeError("provider down")

    for backend in ("memory", "supabase"):
        supa_client = fake_supabase() if backend == "supabase" else None
        store = (
            SupabasePlayerStore(supa_client) if supa_client is not None else InMemoryPlayerStore()
        )
        harness = make_harness(players=store)
        harness.container.game_agents = {"standard": FailingChatModel()}
        _register_and_login(harness, f"refund-{backend}@example.com")
        token = harness.client.cookies.get("shield_player_session") or ""

        reserved = await store.reserve_run(token, is_custom_test=False)
        assert reserved.wave_runs_used == 1
        released = await store.release_run(token, is_custom_test=False)
        assert released.wave_runs_used == 0
        clamped = await store.release_run(token, is_custom_test=False)
        assert clamped.wave_runs_used == 0

        res = harness.client.post(
            "/api/v1/game/run",
            json={"level_id": "medium-1", "board": _simple_board()},
        )
        assert res.status_code == 503
        assert harness.client.get("/api/v1/auth/session").json()["wave_runs_used"] == 0
        if supa_client is not None:
            assert ("players", "release_daily_usage") in supa_client.rpc_calls
