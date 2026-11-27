import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shield_api.container import ConfigurationError, build_container
from shield_api.main import create_app
from shield_api.providers.gemini import GeminiChatModel
from shield_api.services.scores import SupabaseScoreStore
from shield_api.settings import Settings
from shield_engine.adapters.groq import GroqChatModel

from .conftest import FakeClient


def configured(monkeypatch: pytest.MonkeyPatch | None = None, **overrides) -> Settings:
    if monkeypatch is not None:
        monkeypatch.setattr("supabase.create_client", lambda url, key: FakeClient())
    return Settings(
        _env_file=None,
        APP_ENV="development",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_KEY=SecretStr("service-key"),
        **overrides,
    )


@pytest.mark.spec("API-CLEAN-003")
def test_without_provider_keys_the_gateway_degrades_to_offline_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = build_container(configured(monkeypatch))

    assert container.game_agents == {}
    assert isinstance(container.scores, SupabaseScoreStore)


@pytest.mark.spec("API-CLEAN-003")
def test_health_reports_the_storage_backend_and_live_agent_tiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(create_app(build_container(configured(monkeypatch)))) as client:
        body = client.get("/api/v1/health").json()
    assert body["storage_backend"] == "supabase"
    assert body["agent_tiers"] == []


@pytest.mark.spec("API-CLEAN-003")
def test_provider_keys_wire_the_game_agents_and_persistence(monkeypatch) -> None:
    created: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "supabase.create_client", lambda url, key: created.append((url, key)) or FakeClient()
    )

    container = build_container(
        Settings(
            _env_file=None,
            APP_ENV="development",
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
def test_groq_alone_runs_both_agent_tiers(monkeypatch: pytest.MonkeyPatch) -> None:
    container = build_container(configured(monkeypatch, GROQ_API_KEY=SecretStr("groq")))

    assert isinstance(container.game_agents["standard"], GroqChatModel)
    assert isinstance(container.game_agents["budget"], GroqChatModel)


@pytest.mark.spec("API-SUPA-001")
@pytest.mark.parametrize(
    "partial",
    [
        {},
        {"SUPABASE_URL": "https://x.supabase.co"},
        {"SUPABASE_KEY": SecretStr("k")},
    ],
)
def test_missing_or_partial_supabase_raises_configuration_error(partial) -> None:
    with pytest.raises(ConfigurationError):
        build_container(Settings(_env_file=None, **partial))


def test_legacy_anon_key_variable_is_still_accepted(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy")

    assert Settings(_env_file=None).SUPABASE_KEY.get_secret_value() == "legacy"


def test_cors_origins_are_comma_separated(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")

    assert Settings(_env_file=None).CORS_ORIGINS == ["http://a.test", "http://b.test"]


@pytest.mark.spec("API-CHECK-001")
@pytest.mark.parametrize(
    ("model_name", "provider"),
    [
        ("openai/gpt-oss-120b", GroqChatModel),
        ("openai/gpt-oss-safeguard-20b", GroqChatModel),
        ("qwen/qwen3.8-27b", GroqChatModel),
        ("gemini-3.5-flash-lite", GeminiChatModel),
        ("gemma-4-31b-it", GeminiChatModel),
    ],
)
def test_check_models_route_to_the_provider_that_serves_them(
    monkeypatch: pytest.MonkeyPatch, model_name: str, provider: type
) -> None:
    container = build_container(
        configured(monkeypatch, GROQ_API_KEY=SecretStr("groq"), GOOGLE_API_KEY=SecretStr("google"))
    )

    routed = container.check_model_for(model_name)

    assert isinstance(routed, provider)
    assert routed.model == model_name


@pytest.mark.spec("API-CHECK-001")
def test_default_agent_models_are_currently_served() -> None:
    settings = Settings(_env_file=None)

    assert settings.GEMINI_MODEL == "gemini-3.5-flash-lite"
    assert settings.GROQ_CHAT_MODEL == "openai/gpt-oss-120b"
    assert settings.GAME_MODEL_BUDGET == "openai/gpt-oss-20b"


@pytest.mark.spec("API-CHECK-001")
@pytest.mark.parametrize(
    "model_name", ["meta-llama/llama-prompt-guard-2-86m", "meta-llama/llama-prompt-guard-2-22m"]
)
def test_prompt_guard_models_route_to_groq(
    monkeypatch: pytest.MonkeyPatch, model_name: str
) -> None:
    container = build_container(
        configured(monkeypatch, GROQ_API_KEY=SecretStr("groq"), GOOGLE_API_KEY=SecretStr("google"))
    )

    routed = container.check_model_for(model_name)

    assert isinstance(routed, GroqChatModel)
    assert routed.model == model_name


@pytest.mark.spec("API-CHECK-002")
@pytest.mark.parametrize(("thinking", "level"), [(True, "medium"), (False, "minimal")])
async def test_gemini_maps_thinking_to_a_level_and_bills_thought_tokens(
    thinking: bool, level: str
) -> None:
    from shield_engine import ChatMessage

    sent: list[object] = []

    class FakeModels:
        async def generate_content(self, *, model: str, contents: object, config: object) -> object:
            sent.append(config)
            usage = type(
                "Usage",
                (),
                {
                    "prompt_token_count": 10,
                    "candidates_token_count": 5,
                    "thoughts_token_count": 200,
                },
            )()
            return type("Response", (), {"text": "ok", "usage_metadata": usage})()

    model = GeminiChatModel("key", "gemini-3.5-flash-lite")
    model._client = type("Client", (), {"aio": type("Aio", (), {"models": FakeModels()})()})()  # type: ignore[assignment]

    result = await model.complete_with_usage([ChatMessage("user", "hi")], thinking=thinking)

    config = sent[0]
    assert config.thinking_config.thinking_level.lower() == level  # type: ignore[attr-defined]
    assert result.output_tokens == 205


@pytest.mark.spec("API-LADDER-004")
@pytest.mark.parametrize(
    ("model_name", "mime"),
    [("gemini-3.5-flash-lite", "application/json"), ("gemma-4-31b-it", None)],
)
async def test_gemini_asks_for_json_output_so_no_malformed_function_call(
    model_name: str, mime: str | None
) -> None:
    from shield_engine import ChatMessage

    sent: list[object] = []

    class FakeModels:
        async def generate_content(self, *, model: str, contents: object, config: object) -> object:
            sent.append(config)
            return type("Response", (), {"text": "{}", "usage_metadata": None})()

    model = GeminiChatModel("key", model_name)
    model._client = type("Client", (), {"aio": type("Aio", (), {"models": FakeModels()})()})()  # type: ignore[assignment]

    await model.complete_with_usage([ChatMessage("user", "hi")])

    assert sent[0].response_mime_type == mime  # type: ignore[attr-defined]
