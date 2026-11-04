import json
from pathlib import Path

import pytest

from shield_api.demo.tools import CATALOGUE
from shield_api.openapi import DEFAULT_PATH, render
from shield_engine import RiskLevel


@pytest.mark.spec("API-CONTRACT-001")
def test_only_versioned_routes_are_published() -> None:
    paths = json.loads(render())["paths"]

    assert all(path.startswith("/api/v1/") for path in paths)
    assert sorted(paths) == [
        "/api/v1/chat",
        "/api/v1/clearance",
        "/api/v1/feedback",
        "/api/v1/game/levels",
        "/api/v1/game/run",
        "/api/v1/game/scores",
        "/api/v1/game/train",
        "/api/v1/health",
        "/api/v1/predict",
        "/api/v1/requests",
        "/api/v1/screen",
        "/api/v1/stats",
    ]


@pytest.mark.spec("API-CONTRACT-001")
def test_committed_contract_is_up_to_date() -> None:
    committed = Path(DEFAULT_PATH).read_text(encoding="utf-8")

    assert committed == render(), "Contract drifted: run `mise run contract` and commit the result"


@pytest.mark.spec("API-CONTRACT-001")
def test_chat_stream_events_are_published_in_the_contract() -> None:
    schemas = json.loads(render())["components"]["schemas"]

    assert "ChatEvent" in schemas
    assert set(schemas["ChatEvent"]["discriminator"]["mapping"]) == {
        "START", "STAGE_CHANGE", "ML_RESULT", "LLAMAGUARD_RESULT", "DEBATE_TURN", "BLOCK",
        "POLICY_UPDATE", "TOOL_START", "TOOL_END", "FINAL_RESPONSE", "ERROR",
    }  # fmt: skip


DANGEROUS_WORDS = ("delete", "drop", "export", "execute", "sql")


@pytest.mark.spec("API-TOOLS-001")
def test_destructive_demo_tools_are_rated_high_or_critical() -> None:
    dangerous = [t for t in CATALOGUE if any(w in t.name for w in DANGEROUS_WORDS)]

    assert {t.name for t in dangerous} >= {"drop_database_table", "delete_records", "execute_sql"}
    for tool in dangerous:
        assert tool.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}, tool.name
