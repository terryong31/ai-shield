"""Auth flows, browser-bound confirmation, recovery, and hardening (spec 0047)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shield_api.container import ConfigurationError, Container, build_container
from shield_api.main import create_app
from shield_api.openapi import render
from shield_api.services.admins import SupabaseAdminAuthenticator
from shield_api.services.identity import SupabasePlayerIdentity
from shield_api.services.players import InMemoryPlayerStore, SupabasePlayerStore
from shield_api.services.rate_limit import RateLimiter
from shield_api.services.scores import InMemoryScoreStore
from shield_api.services.sessions import AttemptLimiter, InMemorySessionStore
from shield_api.settings import Settings
from shield_engine import Verdict
from shield_engine.testing import StaticClassifier

from .conftest import FakeAuthDirectory, FakeClient, FakeClock, Harness

BROWSER_COOKIE = "shield_auth_browser"
PLAYER_COOKIE = "shield_player_session"
VALID_BROWSER_TOKEN = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
OTHER_BROWSER_TOKEN = "z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4j3i2h1g0"
PASSWORD = "StrongPass1"
NEW_PASSWORD = "NewStrongPass2"
REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "contracts" / "shield-api.openapi.json"


class FakeRedisForAuth:
    """Async Redis test double supporting INCR, EXPIRE, GET, SET, DELETE."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def get(self, key: str) -> str | None:
        if key in self.values:
            return self.values[key]
        if key in self.counts:
            return str(self.counts[key])
        return None

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                removed += 1
            if key in self.counts:
                del self.counts[key]
                removed += 1
        return removed


def _extract_flow_id(redirect_url: str) -> str:
    parsed = urlparse(redirect_url)
    values = parse_qs(parsed.query).get("flow", [])
    assert len(values) == 1
    assert values[0]
    return values[0]


def _prod_container(
    *,
    redis_client: Any = None,
    clock: FakeClock | None = None,
    confirm_email: bool = True,
    web_base_url: str = "https://ai-shield.example",
) -> tuple[TestClient, Container, FakeAuthDirectory, FakeClock]:
    clk = clock or FakeClock()
    auth = FakeAuthDirectory(confirm_email=confirm_email)
    auth.add("admin@example.com", "admin-pass", app_metadata={"provider": "email", "role": "admin"})
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        WEB_BASE_URL=web_base_url,
        SESSION_COOKIE_SECURE=False,
        TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
        TRUSTED_PROXY_SECRET=SecretStr("s3cret"),
        REDIS_URL=SecretStr("redis://localhost:6379/0"),
        MODEL_SIGNING_KEY=SecretStr("test-signing-key"),
    )
    limiter = RateLimiter(redis_client=redis_client, clock=clk)
    container = Container(
        settings=settings,
        classifier=StaticClassifier(Verdict.SAFE, 0.05),
        scores=InMemoryScoreStore(),
        sessions=InMemorySessionStore(),
        players=InMemoryPlayerStore(),
        admins=SupabaseAdminAuthenticator(auth.client),
        identity=SupabasePlayerIdentity(
            auth.client, redirect_to=f"{web_base_url.rstrip('/')}/auth/confirmed"
        ),
        attempts=AttemptLimiter(max_attempts=5, clock=clk),
        rate_limiter=limiter,
    )
    client = TestClient(create_app(container))
    client.__enter__()
    return client, container, auth, clk


def _prod_headers(ip: str = "198.51.100.1", botid: str = "pass") -> dict[str, str]:
    return {
        "x-shield-client-ip": ip,
        "x-shield-proxy-secret": "s3cret",
        "x-shield-botid": botid,
    }


@pytest.mark.spec("API-AUTH-001")
def test_register_binds_browser_cookie_and_flow_id_in_redirect(
    make_harness: Callable[..., Harness], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = make_harness(confirm_email=True)
    harness.client.cookies.set(BROWSER_COOKIE, VALID_BROWSER_TOKEN)

    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": PASSWORD, "player_name": "Ada"},
    )

    assert res.status_code == 202
    assert res.json() == {"status": "confirmation_sent"}
    assert len(harness.auth.sign_ups) == 1
    redirect = harness.auth.sign_ups[0]["options"]["email_redirect_to"]
    assert redirect.startswith(f"{harness.container.settings.WEB_BASE_URL}/auth/confirmed?flow=")
    flow_id = _extract_flow_id(redirect)

    flow_store = getattr(harness.container, "auth_flows", None)
    assert flow_store is not None
    expected_hash = hashlib.sha256(VALID_BROWSER_TOKEN.encode("utf-8")).hexdigest()
    record = flow_store._flows.get(flow_id)
    assert record is not None
    assert record.browser_hash == expected_hash
    assert VALID_BROWSER_TOKEN not in caplog.text


@pytest.mark.spec("API-AUTH-002")
def test_confirm_same_browser_verifies_signs_in_and_clears_flow(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(confirm_email=True)
    harness.client.cookies.set(BROWSER_COOKIE, VALID_BROWSER_TOKEN)
    reg = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": PASSWORD, "player_name": "Ada"},
    )
    assert reg.status_code == 202
    flow_id = _extract_flow_id(harness.auth.sign_ups[0]["options"]["email_redirect_to"])

    confirm_res = harness.client.post(
        "/api/v1/auth/confirm",
        json={
            "flow_id": flow_id,
            "token_hash": "valid-signup-token-ada@example.com",
            "type": "signup",
            "confirm": False,
        },
    )

    assert confirm_res.status_code == 200
    body = confirm_res.json()
    assert body["status"] == "signed_in"
    assert body["session"]["authenticated"] is True
    assert body["session"]["email"] == "ada@example.com"
    assert PLAYER_COOKIE in confirm_res.headers.get("set-cookie", "")
    assert harness.auth.open_sessions == 0
    assert harness.client.get("/api/v1/auth/session").json()["email"] == "ada@example.com"


@pytest.mark.spec("API-AUTH-003")
def test_confirm_different_or_missing_browser_cookie_requires_manual_confirmation(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(confirm_email=True)
    harness.client.cookies.set(BROWSER_COOKIE, VALID_BROWSER_TOKEN)
    harness.client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": PASSWORD, "player_name": "Ada"},
    )
    flow_id = _extract_flow_id(harness.auth.sign_ups[0]["options"]["email_redirect_to"])
    harness.auth.calls.clear()

    # Simulate Outlook scanner (no cookie) and a different browser (different cookie).
    for cookie_val in (None, OTHER_BROWSER_TOKEN):
        harness.client.cookies.clear()
        if cookie_val is not None:
            harness.client.cookies.set(BROWSER_COOKIE, cookie_val)
        res = harness.client.post(
            "/api/v1/auth/confirm",
            json={
                "flow_id": flow_id,
                "token_hash": "valid-signup-token-ada@example.com",
                "type": "signup",
                "confirm": False,
            },
        )
        assert res.status_code == 200
        assert res.json() == {"status": "confirmation_required", "session": None}
        assert PLAYER_COOKIE not in res.headers.get("set-cookie", "")
        assert harness.auth.calls == []

    # Flow was NOT consumed, so the original browser can still auto-confirm.
    harness.client.cookies.clear()
    harness.client.cookies.set(BROWSER_COOKIE, VALID_BROWSER_TOKEN)
    auto = harness.client.post(
        "/api/v1/auth/confirm",
        json={
            "flow_id": flow_id,
            "token_hash": "valid-signup-token-ada@example.com",
            "type": "signup",
            "confirm": False,
        },
    )
    assert auto.status_code == 200
    assert auto.json()["status"] == "signed_in"


@pytest.mark.spec("API-AUTH-004")
def test_confirm_manual_confirmation_verifies_without_signing_in(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(confirm_email=True)
    harness.client.cookies.set(BROWSER_COOKIE, VALID_BROWSER_TOKEN)
    harness.client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": PASSWORD, "player_name": "Ada"},
    )
    flow_id = _extract_flow_id(harness.auth.sign_ups[0]["options"]["email_redirect_to"])

    harness.client.cookies.clear()
    harness.client.cookies.set(BROWSER_COOKIE, OTHER_BROWSER_TOKEN)
    res = harness.client.post(
        "/api/v1/auth/confirm",
        json={
            "flow_id": flow_id,
            "token_hash": "valid-signup-token-ada@example.com",
            "type": "signup",
            "confirm": True,
        },
    )

    assert res.status_code == 200
    assert res.json() == {"status": "confirmed", "session": None}
    assert PLAYER_COOKIE not in res.headers.get("set-cookie", "")
    assert harness.auth.open_sessions == 0
    assert harness.client.get("/api/v1/auth/session").json()["authenticated"] is False


@pytest.mark.spec("API-AUTH-005")
def test_confirm_invalid_expired_or_unavailable_returns_400_or_503(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(confirm_email=True)
    harness.client.cookies.set(BROWSER_COOKIE, VALID_BROWSER_TOKEN)

    bad = harness.client.post(
        "/api/v1/auth/confirm",
        json={"token_hash": "expired-token", "type": "signup", "confirm": True},
    )
    assert bad.status_code == 400
    assert PLAYER_COOKIE not in bad.headers.get("set-cookie", "")

    harness.auth.fail = True
    down = harness.client.post(
        "/api/v1/auth/confirm",
        json={
            "token_hash": "valid-signup-token-ada@example.com",
            "type": "signup",
            "confirm": True,
        },
    )
    assert down.status_code == 503
    assert PLAYER_COOKIE not in down.headers.get("set-cookie", "")


@pytest.mark.spec("API-AUTH-006")
def test_recover_stores_flow_and_passes_reset_password_redirect(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(confirm_email=True)
    harness.client.cookies.set(BROWSER_COOKIE, VALID_BROWSER_TOKEN)

    res = harness.client.post("/api/v1/auth/recover", json={"email": "ada@example.com"})
    assert res.status_code == 200
    assert len(harness.auth.reset_passwords) == 1
    call = harness.auth.reset_passwords[0]
    assert isinstance(call, dict)
    assert call["email"] == "ada@example.com"
    redirect = call["redirect_to"]
    expected_prefix = f"{harness.container.settings.WEB_BASE_URL}/auth/reset-password?flow="
    assert redirect.startswith(expected_prefix)
    flow_id = _extract_flow_id(redirect)
    assert flow_id in harness.container.auth_flows._flows


@pytest.mark.spec("API-AUTH-007")
def test_reset_password_updates_password_revokes_sessions_and_rejects_weak_or_invalid(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(confirm_email=True)
    harness.auth.add("ada@example.com", PASSWORD)
    login = harness.client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    assert harness.client.get("/api/v1/auth/session").json()["authenticated"] is True

    weak = harness.client.post(
        "/api/v1/auth/reset-password",
        json={"token_hash": "valid-recovery-token-ada@example.com", "new_password": "weak"},
    )
    assert weak.status_code == 422

    bad = harness.client.post(
        "/api/v1/auth/reset-password",
        json={"token_hash": "expired-token", "new_password": NEW_PASSWORD},
    )
    assert bad.status_code == 400

    ok = harness.client.post(
        "/api/v1/auth/reset-password",
        json={"token_hash": "valid-recovery-token-ada@example.com", "new_password": NEW_PASSWORD},
    )
    assert ok.status_code == 200
    assert ok.json() == {"status": "password_reset"}
    assert harness.auth.open_sessions == 0
    # Existing gateway session must be revoked.
    assert harness.client.get("/api/v1/auth/session").json()["authenticated"] is False

    # New password works for login.
    new_login = harness.client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200


@pytest.mark.spec("API-AUTH-008")
def test_email_change_passes_redirect_and_enforces_production_rate_limit() -> None:
    redis = FakeRedisForAuth()
    client, _container, auth, _clk = _prod_container(redis_client=redis)
    with client:
        auth.add("ada@example.com", PASSWORD)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": PASSWORD},
            headers=_prod_headers(),
        )
        assert login.status_code == 200

        for idx in range(5):
            res = client.post(
                "/api/v1/auth/account/email",
                json={"new_email": f"new{idx}@example.com", "current_password": PASSWORD},
                headers=_prod_headers(),
            )
            assert res.status_code == 202

        assert len(auth.email_change_redirects) == 5
        assert auth.email_change_redirects[0].startswith(
            "https://ai-shield.example/auth/confirmed?flow="
        )
        assert "&intent=email_change" in auth.email_change_redirects[0]

        limited = client.post(
            "/api/v1/auth/account/email",
            json={"new_email": "new6@example.com", "current_password": PASSWORD},
            headers=_prod_headers(),
        )
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1


@pytest.mark.spec("API-AUTH-009")
def test_unconfirmed_login_does_not_penalize_login_fail_rate_limit() -> None:
    redis = FakeRedisForAuth()
    client, _container, auth, _clk = _prod_container(redis_client=redis, confirm_email=True)
    with client:
        user = auth.add("unconfirmed@example.com", PASSWORD)
        auth.email_confirmed[user.id] = False

        for idx in range(11):
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "unconfirmed@example.com", "password": PASSWORD},
                headers=_prod_headers(ip=f"198.51.100.{idx + 1}"),
            )
            assert res.status_code == 403
            assert res.json()["detail"] == "Confirm your email before signing in."


@pytest.mark.spec("API-AUTH-010")
def test_redis_backed_attempt_limiting_shares_failures_across_containers() -> None:
    redis = FakeRedisForAuth()
    clk = FakeClock()
    client1, *_ = _prod_container(redis_client=redis, clock=clk)
    client2, *_ = _prod_container(redis_client=redis, clock=clk)
    with client1, client2:
        for idx in range(5):
            target = client1 if idx % 2 == 0 else client2
            res = target.post(
                "/api/v1/clearance",
                json={"email": "admin@example.com", "password": "wrong"},
                headers=_prod_headers(ip="203.0.113.50"),
            )
            assert res.status_code == 401

        blocked = client2.post(
            "/api/v1/clearance",
            json={"email": "admin@example.com", "password": "admin-pass"},
            headers=_prod_headers(ip="203.0.113.50"),
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1


@pytest.mark.spec("API-AUTH-011")
def test_register_returns_503_on_supabase_outage_and_202_on_existing_email(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(confirm_email=True)
    first = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": PASSWORD, "player_name": "Ada"},
    )
    assert first.status_code == 202

    dup = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": PASSWORD, "player_name": "Ada"},
    )
    assert dup.status_code == 202
    assert dup.json() == {"status": "confirmation_sent"}

    harness.auth.fail = True
    outage = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": PASSWORD, "player_name": "Grace"},
    )
    assert outage.status_code == 503


@pytest.mark.spec("API-AUTH-012")
def test_production_botid_protects_recover_resend_confirm_and_reset_password() -> None:
    redis = FakeRedisForAuth()
    client, *_ = _prod_container(redis_client=redis)
    with client:
        for path, body in [
            ("/api/v1/auth/recover", {"email": "ada@example.com"}),
            ("/api/v1/auth/resend-confirmation", {"email": "ada@example.com"}),
            ("/api/v1/auth/confirm", {"token_hash": "tok", "confirm": True}),
            ("/api/v1/auth/reset-password", {"token_hash": "tok", "new_password": NEW_PASSWORD}),
        ]:
            blocked = client.post(path, json=body, headers={"x-shield-client-ip": "198.51.100.1"})
            assert blocked.status_code == 403, path
            assert blocked.json() == {"detail": "Request blocked."}


@pytest.mark.spec("API-AUTH-013")
@pytest.mark.asyncio
async def test_supabase_player_store_prunes_expired_sessions_on_insert(fake_supabase) -> None:
    client = fake_supabase()
    store = SupabasePlayerStore(client)
    now = datetime.now(UTC)
    client.schema("players").table("sessions").insert(
        {
            "token_hash": "expired-hash",
            "email": None,
            "is_anonymous": True,
            "player_name": "Anonymous",
            "tier": "anonymous",
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "expires_at": (now - timedelta(hours=1)).isoformat(),
        }
    ).execute()

    await store.create_anonymous(timedelta(hours=1))
    rows = client.tables[("players", "sessions")].rows
    assert all(row["token_hash"] != "expired-hash" for row in rows)
    assert len(rows) == 1


@pytest.mark.spec("API-AUTH-014")
def test_production_build_container_requires_non_localhost_web_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeClient()
    monkeypatch.setattr("supabase.create_client", lambda url, key: fake)
    monkeypatch.setattr("redis.asyncio.from_url", lambda url, **kw: FakeRedisForAuth())

    for bad_url in ("", "   ", "http://localhost:3000", "http://127.0.0.1:3000"):
        with pytest.raises(ConfigurationError) as exc:
            build_container(
                Settings(
                    _env_file=None,
                    APP_ENV="production",
                    WEB_BASE_URL=bad_url,
                    SUPABASE_URL="https://example.supabase.co",
                    SUPABASE_KEY=SecretStr("service-key"),
                    REDIS_URL=SecretStr("redis://localhost:6379/0"),
                    TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
                    TRUSTED_PROXY_SECRET=SecretStr("s3cret"),
                )
            )
        assert "WEB_BASE_URL" in str(exc.value)

    container = build_container(
        Settings(
            _env_file=None,
            APP_ENV="production",
            WEB_BASE_URL="https://ai-shield-delta.vercel.app/",
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
            REDIS_URL=SecretStr("redis://localhost:6379/0"),
            TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
            TRUSTED_PROXY_SECRET=SecretStr("s3cret"),
        )
    )
    assert isinstance(container.identity, SupabasePlayerIdentity)
    assert container.identity._redirect_to == "https://ai-shield-delta.vercel.app/auth/confirmed"


@pytest.mark.spec("API-AUTH-015")
def test_contract_includes_confirm_and_reset_password_and_auth_responses_are_no_store(
    make_harness: Callable[..., Harness],
) -> None:
    committed = CONTRACT.read_text(encoding="utf-8")
    assert json.loads(render()) == json.loads(committed)
    contract = json.loads(committed)
    paths = contract["paths"]
    assert "post" in paths["/api/v1/auth/confirm"]
    assert "post" in paths["/api/v1/auth/reset-password"]

    harness = make_harness()
    assert harness.client.get("/api/v1/auth/session").headers.get("cache-control") == "no-store"
    assert harness.client.get("/api/v1/clearance").headers.get("cache-control") == "no-store"
