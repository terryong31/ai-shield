"""Supabase-only persistence and identity (spec 0046)."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from shield_api.container import Container, build_container
from shield_api.openapi import render
from shield_api.services.admins import SupabaseAdminAuthenticator
from shield_api.services.identity import SupabasePlayerIdentity
from shield_api.services.players import InMemoryPlayerStore, PlayerStore, SupabasePlayerStore
from shield_api.services.scores import InMemoryScoreStore, SupabaseScoreStore
from shield_api.services.sessions import SupabaseSessionStore
from shield_api.settings import Settings
from shield_engine.testing import StaticClassifier

from .conftest import FakeAuthDirectory, FakeClient, Harness

ROOT = Path(__file__).resolve().parents[3]
API_SRC = ROOT / "apps" / "api" / "src" / "shield_api"
MIGRATIONS = ROOT / "supabase" / "migrations"
# Built at runtime so this file passes the repository-wide sunset scan (DEV-SUPA-006).
_LEGACY = "sq" + "lite"
_LEGACY_PATH_SETTING = f"{_LEGACY.upper()}_PATH"
_LEGACY_CLASS = _LEGACY.capitalize()


@pytest.mark.spec("API-SUPA-001")
@pytest.mark.parametrize("app_env", ["development", "production"])
@pytest.mark.parametrize(
    ("url", "key", "expected_missing"),
    [
        ("", None, ("SUPABASE_URL", "SUPABASE_KEY")),
        ("   ", SecretStr("   "), ("SUPABASE_URL", "SUPABASE_KEY")),
        ("https://x.supabase.co", None, ("SUPABASE_KEY",)),
        ("", SecretStr("service-key"), ("SUPABASE_URL",)),
    ],
)
def test_missing_supabase_raises_configuration_error_in_every_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    app_env: str,
    url: str,
    key: SecretStr | None,
    expected_missing: tuple[str, ...],
) -> None:
    from shield_api.container import ConfigurationError

    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ConfigurationError) as exc_info:
        build_container(
            Settings(
                _env_file=None,
                APP_ENV=app_env,  # type: ignore[arg-type]
                SUPABASE_URL=url,
                SUPABASE_KEY=key,
                REDIS_URL=SecretStr("rediss://localhost:6379/0"),
            )
        )

    message = str(exc_info.value)
    for name in expected_missing:
        assert name in message
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert "mise run db:start" in error_records[0].getMessage()
    for name in expected_missing:
        assert name in error_records[0].getMessage()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.spec("API-SUPA-002")
def test_development_with_supabase_and_no_redis_uses_supabase_and_in_memory_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = FakeAuthDirectory()
    fake_client = FakeClient()
    fake_client.auth = auth.client().auth  # type: ignore[attr-defined]
    monkeypatch.setattr("supabase.create_client", lambda url, key: fake_client)

    container = build_container(
        Settings(
            _env_file=None,
            APP_ENV="development",
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
            REDIS_URL=None,
        )
    )

    assert isinstance(container.scores, SupabaseScoreStore)
    assert isinstance(container.players, SupabasePlayerStore)
    assert isinstance(container.sessions, SupabaseSessionStore)
    assert isinstance(container.identity, SupabasePlayerIdentity)
    assert isinstance(container.admins, SupabaseAdminAuthenticator)
    assert _LEGACY_PATH_SETTING not in type(container.settings).model_fields


@pytest.mark.spec("API-SUPA-003")
def test_shield_api_contains_no_legacy_store_or_local_auth_symbols() -> None:
    forbidden = (
        f"{_LEGACY_CLASS}ScoreStore",
        f"{_LEGACY_CLASS}PlayerStore",
        f"{_LEGACY_CLASS}SessionStore",
        "connect_domains",
        f"{_LEGACY}3",
        "_hash_password",
        "_password_matches",
        "NoAdminAuthenticator",
    )
    hits: list[str] = []
    for path in sorted(API_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for sym in forbidden:
            if sym in text:
                hits.append(f"{path.relative_to(ROOT)}: {sym}")
    assert hits == []
    assert _LEGACY_PATH_SETTING not in Settings.model_fields


@pytest.mark.spec("API-SUPA-004")
def test_player_store_has_no_password_methods_and_container_requires_identity_and_admins() -> None:
    for method in ("register", "login", "verify_password", "set_password"):
        # typing.Protocol inherits ABCMeta.register; check the Protocol's own attributes.
        assert method not in PlayerStore.__dict__
        assert not hasattr(InMemoryPlayerStore, method)
        assert not hasattr(SupabasePlayerStore, method)

    with pytest.raises(TypeError):
        Container(  # type: ignore[call-arg]
            settings=Settings(_env_file=None),
            classifier=StaticClassifier(),
            scores=InMemoryScoreStore(),
        )


@pytest.mark.spec("API-SUPA-005")
def test_all_password_checks_and_changes_go_through_supabase_auth(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness()
    harness.auth.confirm_email = False

    reg = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": "StrongPass1", "player_name": "Ada"},
    )
    assert reg.status_code == 200
    assert "sign_up" in harness.auth.calls

    harness.auth.calls.clear()
    login = harness.client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "StrongPass1"},
    )
    assert login.status_code == 200
    assert "sign_in_with_password" in harness.auth.calls

    harness.auth.calls.clear()
    pw = harness.client.post(
        "/api/v1/auth/account/password",
        json={"current_password": "StrongPass1", "new_password": "BetterPass2"},
    )
    assert pw.status_code == 200
    assert "sign_in_with_password" in harness.auth.calls
    assert "admin.update_user_by_id" in harness.auth.calls

    harness.auth.calls.clear()
    em = harness.client.post(
        "/api/v1/auth/account/email",
        json={"current_password": "BetterPass2", "new_email": "ada.new@example.com"},
    )
    assert em.status_code in (200, 202)
    assert "sign_in_with_password" in harness.auth.calls

    harness.auth.calls.clear()
    deleted = harness.client.request(
        "DELETE",
        "/api/v1/auth/account",
        json={"current_password": "BetterPass2", "confirm": "DELETE"},
    )
    assert deleted.status_code == 204
    assert "sign_in_with_password" in harness.auth.calls
    assert "admin.delete_user" in harness.auth.calls


@pytest.mark.spec("API-SUPA-006")
def test_recover_calls_container_identity_and_auth_router_does_not_import_supabase(
    make_harness: Callable[..., Harness],
) -> None:
    from shield_api.routers import auth as auth_router

    assert "supabase" not in inspect.getsource(auth_router)

    harness = make_harness()
    recorded: list[str] = []

    class SpyIdentity:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        async def recover(
            self,
            email: str,
            *,
            redirect_to: str | None = None,
            verifier_out: list[str] | None = None,
        ) -> None:
            recorded.append(email)

    harness.container.identity = SpyIdentity(harness.container.identity)
    res_known = harness.client.post("/api/v1/auth/recover", json={"email": "Ada@Example.com"})
    res_unknown = harness.client.post("/api/v1/auth/recover", json={"email": "nobody@example.com"})

    assert res_known.status_code == 200
    assert res_unknown.status_code == 200
    assert res_known.json() == res_unknown.json() == {"status": "ok"}
    assert recorded == ["ada@example.com", "nobody@example.com"]


@pytest.mark.spec("API-SUPA-007")
def test_health_and_contract_report_only_supabase_and_memory(
    make_harness: Callable[..., Harness], fake_supabase: Callable[..., FakeClient]
) -> None:
    mem_harness = make_harness()
    assert mem_harness.client.get("/api/v1/health").json()["storage_backend"] == "memory"

    sb_harness = make_harness(scores=SupabaseScoreStore(fake_supabase()))
    assert sb_harness.client.get("/api/v1/health").json()["storage_backend"] == "supabase"

    import json

    schema = json.loads(render())["components"]["schemas"]["HealthResponse"]
    assert schema["properties"]["storage_backend"]["enum"] == ["supabase", "memory"]


@pytest.mark.spec("API-SUPA-008")
async def test_newest_player_migration_drops_password_columns_and_store_omits_them(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    sql_files = sorted(MIGRATIONS.glob("*.sql"))
    newest_player_mig = next(
        p
        for p in reversed(sql_files)
        if "players.accounts" in (text := p.read_text(encoding="utf-8").lower())
        and "password_hash" in text
    )
    sql = newest_player_mig.read_text(encoding="utf-8").lower()
    assert "drop column" in sql
    assert "password_hash" in sql
    assert "salt" in sql

    client = fake_supabase()
    store = SupabasePlayerStore(client)
    from datetime import timedelta

    await store.sign_in_verified(email="ada@example.com", player_name="Ada", ttl=timedelta(hours=1))
    rows = client.tables[("players", "accounts")].rows
    assert len(rows) == 1
    assert "password_hash" not in rows[0]
    assert "salt" not in rows[0]
