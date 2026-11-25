import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from shield_api.openapi import render
from shield_api.services.clearance import Clearance, clearance_for
from shield_api.services.sessions import AttemptLimiter, InMemorySessionStore, SupabaseSessionStore
from shield_api.settings import Settings

COOKIE = "shield_session"
ORIGIN = "http://localhost:3000"
CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "shield-api.openapi.json"


def set_cookie(response) -> str:
    return response.headers.get("set-cookie", "")


def admin_allowed(harness) -> bool:
    """Admin clearance gates the scoreboard reset, the gateway's admin-only route."""
    status = harness.client.delete("/api/v1/game/scores").status_code
    assert status in (204, 401)
    return status == 204


@pytest.mark.spec("API-CLEAR-014")
def test_an_admin_account_is_granted_a_session_cookie(harness, admin_password: str) -> None:
    response = harness.grant(admin_password)

    assert response.status_code == 200
    body = response.json()
    assert body["granted"] is True
    expires_at = datetime.fromisoformat(body["expires_at"])
    expected = datetime.now(UTC) + timedelta(minutes=harness.container.settings.SESSION_TTL_MINUTES)
    assert abs((expires_at - expected).total_seconds()) < 5
    header = set_cookie(response).lower()
    assert header.startswith(f"{COOKIE}=")
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/api/v1" in header
    assert admin_allowed(harness)


@pytest.mark.spec("API-CLEAR-014")
def test_the_admin_email_matches_case_insensitively(harness, admin_password: str) -> None:
    assert harness.grant(admin_password, email="Admin@Example.com").status_code == 200


@pytest.mark.spec("API-CLEAR-015")
def test_every_refusal_is_the_same_generic_401(make_harness, admin_password: str) -> None:
    harness = make_harness()
    harness.auth.add("player@example.com", "PlayerPass1", app_metadata={"provider": "email"})
    harness.auth.add("sneaky@example.com", "sneaky-pass", user_metadata={"role": "admin"})
    harness.client.post(
        "/api/v1/auth/register",
        json={"email": "player@example.com", "password": "PlayerPass1", "player_name": "Pat"},
    )
    down = make_harness()
    down.auth.fail = True

    refusals = [
        harness.grant("wrong password"),
        harness.grant(admin_password, email="nobody@example.com"),
        harness.grant("PlayerPass1", email="player@example.com"),
        harness.grant("sneaky-pass", email="sneaky@example.com"),
        down.grant(admin_password),
    ]

    assert {r.status_code for r in refusals} == {401}
    assert len({r.json()["detail"] for r in refusals}) == 1
    assert {set_cookie(r) for r in refusals} == {""}
    assert not admin_allowed(harness)


@pytest.mark.spec("API-CLEAR-016")
def test_neither_password_nor_token_is_persisted_or_logged(
    make_harness, admin_password: str, fake_supabase, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = fake_supabase()
    harness = make_harness(sessions=SupabaseSessionStore(client))
    harness.auth.add("player@example.com", "player-pass")

    harness.grant("wrong guess")
    harness.grant("player-pass", email="player@example.com")
    token = harness.grant(admin_password).cookies[COOKIE]
    admin_allowed(harness)

    rows = client.tables[("audit", "clearance_sessions")].rows
    serialized = json.dumps(rows)
    for secret in (admin_password, "wrong guess", "player-pass", token):
        assert secret not in serialized
        assert secret not in caplog.text
    hashes = [row["token_hash"] for row in rows]
    assert hashes == [hashlib.sha256(token.encode()).hexdigest()]
    assert len(harness.auth.sign_ins) == 3
    assert harness.auth.open_sessions == 0


@pytest.mark.spec("API-CLEAR-017")
def test_repeated_failures_are_rate_limited(harness, admin_password: str) -> None:
    limit = harness.container.settings.CLEARANCE_MAX_ATTEMPTS
    for _ in range(limit):
        assert harness.grant("guess").status_code == 401
    calls = len(harness.auth.sign_ins)

    blocked = harness.grant(admin_password)

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert set_cookie(blocked) == ""
    assert len(harness.auth.sign_ins) == calls


@pytest.mark.spec("API-CLEAR-017")
def test_a_successful_grant_resets_the_failure_count(harness, admin_password: str) -> None:
    limit = harness.container.settings.CLEARANCE_MAX_ATTEMPTS
    for _ in range(limit - 1):
        harness.grant("guess")
    assert harness.grant(admin_password).status_code == 200

    for _ in range(limit - 1):
        assert harness.grant("guess").status_code == 401
    assert harness.grant("guess").status_code == 401


@pytest.mark.spec("API-CLEAR-017")
def test_the_limit_lifts_after_the_window(harness, admin_password: str) -> None:
    for _ in range(harness.container.settings.CLEARANCE_MAX_ATTEMPTS):
        harness.grant("guess")

    harness.clock.advance(harness.container.settings.CLEARANCE_WINDOW_MINUTES * 60 + 1)

    assert harness.grant(admin_password).status_code == 200


@pytest.mark.spec("API-CLEAR-018")
def test_the_shared_passphrase_is_gone(harness) -> None:
    assert "SECURE_PASSPHRASE" not in Settings.model_fields

    response = harness.client.post("/api/v1/clearance", json={"passphrase": "anything"})

    assert response.status_code == 422
    for contract in (json.loads(render()), json.loads(CONTRACT.read_text(encoding="utf-8"))):
        request = contract["components"]["schemas"]["ClearanceRequest"]
        assert set(request["properties"]) == {"email", "password"}
        assert set(request["required"]) == {"email", "password"}


@pytest.mark.spec("API-CLEAN-003")
def test_live_session_unlocks_the_admin_route(harness, admin_password: str) -> None:
    harness.grant(admin_password)

    assert admin_allowed(harness)


@pytest.mark.spec("API-CLEAN-003")
def test_missing_unknown_or_expired_cookie_means_no_clearance(harness) -> None:
    assert not admin_allowed(harness)

    harness.client.cookies.set(COOKIE, "not-a-real-token")
    assert not admin_allowed(harness)

    expired, _ = asyncio.run(harness.sessions.create(timedelta(seconds=-1)))
    harness.client.cookies.set(COOKIE, expired)
    assert not admin_allowed(harness)


@pytest.mark.spec("API-CLEAR-005")
def test_revoking_ends_the_session(harness, admin_password: str) -> None:
    token = harness.grant(admin_password).cookies[COOKIE]

    response = harness.client.delete("/api/v1/clearance")

    assert response.status_code == 204
    header = set_cookie(response).lower()
    assert header.startswith(f"{COOKIE}=")
    assert "max-age=0" in header or "expires=thu, 01 jan 1970" in header
    assert asyncio.run(harness.sessions.lookup(token)) is None
    harness.client.cookies.set(COOKIE, token)
    assert not admin_allowed(harness)


@pytest.mark.spec("API-CLEAR-005")
def test_revoking_without_a_session_is_a_no_op(harness) -> None:
    assert harness.client.delete("/api/v1/clearance").status_code == 204


@pytest.mark.spec("API-CLEAR-006")
def test_status_reports_the_live_session(harness, admin_password: str) -> None:
    assert harness.client.get("/api/v1/clearance").json() == {"granted": False, "expires_at": None}

    granted = harness.grant(admin_password).json()
    status = harness.client.get("/api/v1/clearance").json()

    assert status["granted"] is True
    assert datetime.fromisoformat(status["expires_at"]) == datetime.fromisoformat(
        granted["expires_at"]
    )


@pytest.mark.spec("API-CLEAN-003")
def test_contract_publishes_clearance() -> None:
    contract = json.loads(render())
    schemas = contract["components"]["schemas"]

    assert {"get", "post", "delete"} <= set(contract["paths"]["/api/v1/clearance"])
    assert set(schemas["ClearanceStatus"]["properties"]) == {"granted", "expires_at"}


@pytest.mark.spec("API-CLEAR-010")
@pytest.mark.parametrize(
    "origin",
    [
        ORIGIN,
        "http://127.0.0.1:3000",
        "http://[::1]:3000",
        "http://[::]:3000",
    ],
)
def test_cors_allows_credentialed_delete_only_for_known_origins(harness, origin: str) -> None:
    preflight = {"Access-Control-Request-Method": "DELETE"}

    allowed = harness.client.options("/api/v1/clearance", headers={"Origin": origin, **preflight})
    foreign = harness.client.options(
        "/api/v1/clearance", headers={"Origin": "https://evil.example", **preflight}
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == origin
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "DELETE" in allowed.headers["access-control-allow-methods"]
    assert "access-control-allow-origin" not in foreign.headers


@pytest.mark.spec("API-CLEAN-003")
async def test_a_recent_failed_guess_means_denied_until_the_window_passes() -> None:
    now = [1_000.0]
    attempts = AttemptLimiter(max_attempts=5, window=timedelta(minutes=10), clock=lambda: now[0])
    sessions = InMemorySessionStore()
    attempts.record_failure("1.2.3.4")

    assert await clearance_for(None, "1.2.3.4", sessions, attempts) is Clearance.DENIED
    token, _ = await sessions.create(timedelta(hours=1))
    assert await clearance_for(token, "1.2.3.4", sessions, attempts) is Clearance.GRANTED

    now[0] += 10 * 60 + 1
    assert await clearance_for(None, "1.2.3.4", sessions, attempts) is Clearance.NONE


@pytest.mark.spec("API-CLEAR-012")
def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CORS_ORIGINS="*")


class ExplodingSessions:
    async def create(self, ttl: timedelta) -> tuple[str, datetime]:
        raise RuntimeError("disk full")

    async def lookup(self, token: str) -> datetime | None:
        raise RuntimeError("disk full")

    async def revoke(self, token: str) -> None:
        raise RuntimeError("disk full")


@pytest.mark.spec("API-CLEAN-003")
def test_session_store_failure_fails_closed(make_harness, caplog: pytest.LogCaptureFixture) -> None:
    harness = make_harness(sessions=ExplodingSessions())
    harness.client.cookies.set(COOKIE, "some-token")

    assert not admin_allowed(harness)
    assert harness.client.get("/api/v1/game/levels").status_code == 200
    assert any(r.exc_info and "disk full" in str(r.exc_info[1]) for r in caplog.records)
