from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shield_api.container import build_container
from shield_api.main import create_app
from shield_api.providers.gemini import GeminiChatModel
from shield_api.services.scores import SqliteScoreStore, SupabaseScoreStore
from shield_api.settings import Settings
from shield_engine.adapters.groq import GroqChatModel


def offline(tmp_path: Path, **overrides) -> Settings:
    return Settings(_env_file=None, SQLITE_PATH=tmp_path / "var" / "shield.db", **overrides)


@pytest.mark.spec("API-CLEAN-003")
def test_without_provider_keys_the_gateway_degrades_to_offline_defaults(tmp_path: Path) -> None:
    container = build_container(offline(tmp_path))

    assert container.game_agents == {}
    assert isinstance(container.scores, SqliteScoreStore)
    assert (tmp_path / "var" / "shield.game.db").exists()


@pytest.mark.spec("API-CLEAN-003")
@pytest.mark.parametrize(
    "partial",
    [{"SUPABASE_URL": "https://x.supabase.co"}, {"SUPABASE_KEY": SecretStr("k")}],
)
def test_half_configured_supabase_falls_back_to_sqlite(tmp_path: Path, partial) -> None:
    assert isinstance(build_container(offline(tmp_path, **partial)).scores, SqliteScoreStore)


@pytest.mark.spec("API-CLEAN-003")
def test_health_reports_the_storage_backend_and_live_agent_tiers(tmp_path: Path) -> None:
    with TestClient(create_app(build_container(offline(tmp_path)))) as client:
        body = client.get("/api/v1/health").json()
    assert body["storage_backend"] == "sqlite"
    assert body["agent_tiers"] == []


@pytest.mark.spec("API-CLEAN-003")
def test_provider_keys_wire_the_game_agents_and_persistence(tmp_path: Path, monkeypatch) -> None:
    created: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "supabase.create_client", lambda url, key: created.append((url, key)) or object()
    )

    container = build_container(
        Settings(
            _env_file=None,
            GROQ_API_KEY=SecretStr("groq"),
            GOOGLE_API_KEY=SecretStr("google"),
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
        )
    )

    assert isinstance(container.scores, SupabaseScoreStore)
    assert created == [("https://example.supabase.co", "service-key")]
    # Gemini runs the standard tier when a Google key is set; Groq runs the budget tier.
    assert isinstance(container.game_agents["standard"], GeminiChatModel)
    assert isinstance(container.game_agents["budget"], GroqChatModel)


@pytest.mark.spec("API-CLEAN-003")
def test_groq_alone_runs_both_agent_tiers(tmp_path: Path) -> None:
    container = build_container(offline(tmp_path, GROQ_API_KEY=SecretStr("groq")))

    assert isinstance(container.game_agents["standard"], GroqChatModel)
    assert isinstance(container.game_agents["budget"], GroqChatModel)


def test_legacy_anon_key_variable_is_still_accepted(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy")

    assert Settings(_env_file=None).SUPABASE_KEY.get_secret_value() == "legacy"


def test_cors_origins_are_comma_separated(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")

    assert Settings(_env_file=None).CORS_ORIGINS == ["http://a.test", "http://b.test"]
