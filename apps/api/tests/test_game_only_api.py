"""The gateway serves only the game and its admin console (spec 0026)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from shield_api.openapi import render
from shield_api.schemas import ScoreCreateRequest
from shield_api.services.scores import SupabaseScoreStore

from .conftest import FakeClient, Harness

ROOT = Path(__file__).resolve().parents[3]
REMOVED_ROUTES = (
    ("post", "/api/v1/chat"),
    ("post", "/api/v1/screen"),
    ("post", "/api/v1/predict"),
    ("get", "/api/v1/requests"),
    ("get", "/api/v1/stats"),
    ("post", "/api/v1/feedback"),
)
LEGACY_SCHEMAS = {
    "ChatRequest", "ScreenRequest", "ScreenResponse", "PredictRequest", "PredictResponse",
    "StatsResponse", "FeedbackRequest", "FeedbackResponse", "AuditRecord", "DecisionLayer",
    "ToolPolicy", "Verdict",
}  # fmt: skip


def _score() -> ScoreCreateRequest:
    return ScoreCreateRequest(
        player_name="Ada",
        level_id="easy-1",
        total_score=9000,
        medal="gold",
        attacks_blocked=4,
        attacks_total=4,
        false_alarms=0,
        avg_latency_ms=1.0,
        total_cost_usd=0.0,
        board={"nodes": [], "edges": []},  # type: ignore[arg-type]
    )


@pytest.mark.spec("API-CLEAN-001")
@pytest.mark.parametrize(("method", "path"), REMOVED_ROUTES)
def test_removed_routes_return_404(harness: Harness, method: str, path: str) -> None:
    send = getattr(harness.client, method)
    response = send(path, json={"message": "hi"}) if method == "post" else send(path)
    assert response.status_code == 404


@pytest.mark.spec("API-CLEAN-001")
def test_contract_lists_only_game_auth_clearance_and_health_paths() -> None:
    paths = json.loads(render())["paths"]
    allowed = (
        "/api/v1/health",
        "/api/v1/auth/",
        "/api/v1/billing/",  # spec 0049
        "/api/v1/game/",
        "/api/v1/clearance",
    )
    assert paths
    assert all(p.startswith(allowed) for p in paths), sorted(paths)


@pytest.mark.spec("API-CLEAN-002")
def test_contract_has_no_legacy_component_schemas() -> None:
    schemas = json.loads(render())["components"]["schemas"]
    # The chat stream's events were all named ``*Event``; no game schema is.
    legacy = [name for name in schemas if name in LEGACY_SCHEMAS or name.endswith("Event")]
    assert legacy == []


@pytest.mark.spec("API-CLEAN-003")
def test_the_game_auth_clearance_and_health_routes_still_work(
    harness: Harness, admin_password: str
) -> None:
    client = harness.client
    # The kept routes must keep working in the cleaned-up gateway, not alongside the old one.
    assert client.post("/api/v1/chat", json={"message": "hi"}).status_code == 404
    assert client.get("/api/v1/health").status_code == 200
    assert client.post("/api/v1/auth/anonymous").status_code == 200
    assert client.get("/api/v1/game/levels").status_code == 200
    assert client.get("/api/v1/game/scores").status_code == 200
    assert harness.grant(admin_password).status_code == 200
    assert client.get("/api/v1/clearance").json()["granted"] is True
    assert client.delete("/api/v1/game/scores").status_code == 204


@pytest.mark.spec("API-CLEAN-004")
async def test_supabase_never_touches_audit_requests(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    client = fake_supabase()
    await SupabaseScoreStore(client).record_score(_score())
    assert ("audit", "requests") not in client.accessed

    migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    drop = [m for m in migrations if "drop table if exists audit.requests" in m.read_text().lower()]
    assert drop
    assert "audit.requests" not in (ROOT / "supabase" / "seed.sql").read_text()
