from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shield_api.container import build_container
from shield_api.demo.gemini import GeminiChatModel
from shield_api.main import create_app
from shield_api.services.audit import SqliteAuditLog, SupabaseAuditLog
from shield_api.settings import Settings
from shield_engine import DebateAdjudicator, LlamaGuardModerator


def offline(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        FEEDBACK_PATH=tmp_path / "f.csv",
        SQLITE_PATH=tmp_path / "var" / "shield.db",
        **overrides,
    )


@pytest.mark.spec("API-STORE-001")
def test_without_provider_keys_the_gateway_degrades_to_offline_defaults(tmp_path: Path) -> None:
    container = build_container(offline(tmp_path))

    assert container.shield.moderator is None
    assert container.shield.adjudicator is None
    assert isinstance(container.audit_log, SqliteAuditLog)
    assert (tmp_path / "var" / "shield.db").exists()
    assert container.assistant.models == []


@pytest.mark.spec("API-STORE-004")
@pytest.mark.parametrize(
    "partial",
    [{"SUPABASE_URL": "https://x.supabase.co"}, {"SUPABASE_KEY": SecretStr("k")}],
)
def test_half_configured_supabase_falls_back_to_sqlite(tmp_path: Path, partial) -> None:
    assert isinstance(build_container(offline(tmp_path, **partial)).audit_log, SqliteAuditLog)


@pytest.mark.spec("API-STORE-005")
def test_health_reports_the_active_audit_backend(tmp_path: Path) -> None:
    with TestClient(create_app(build_container(offline(tmp_path)))) as client:
        assert client.get("/api/v1/health").json()["audit_backend"] == "sqlite"


@pytest.mark.spec("API-STORE-004")
def test_provider_keys_wire_the_llm_layers_and_persistence(tmp_path: Path, monkeypatch) -> None:
    created: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "supabase.create_client", lambda url, key: created.append((url, key)) or object()
    )

    container = build_container(
        Settings(
            _env_file=None,
            FEEDBACK_PATH=tmp_path / "f.csv",
            GROQ_API_KEY=SecretStr("groq"),
            GOOGLE_API_KEY=SecretStr("google"),
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
        )
    )

    assert isinstance(container.shield.moderator, LlamaGuardModerator)
    assert isinstance(container.shield.adjudicator, DebateAdjudicator)
    assert isinstance(container.audit_log, SupabaseAuditLog)
    assert created == [("https://example.supabase.co", "service-key")]
    # Gemini answers first; Groq is the fallback.
    assert isinstance(container.assistant.models[0], GeminiChatModel)
    assert len(container.assistant.models) == 2


def test_legacy_anon_key_variable_is_still_accepted(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy")

    assert Settings(_env_file=None).SUPABASE_KEY.get_secret_value() == "legacy"


def test_cors_origins_are_comma_separated(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")

    assert Settings(_env_file=None).CORS_ORIGINS == ["http://a.test", "http://b.test"]
