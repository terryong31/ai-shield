import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from shield_api.openapi import render
from shield_api.schemas import ChatRequest, ScreenRequest
from shield_api.services.sessions import SqliteSessionStore
from shield_api.settings import Settings
from shield_engine import Clearance

COOKIE = "shield_session"
ORIGIN = "http://localhost:3000"


def set_cookie(response) -> str:
    return response.headers.get("set-cookie", "")


def clearance_seen(harness, message: str = "hello") -> Clearance:
    """The clearance the engine saw: a SAFE prompt is adjudicated only when one is claimed."""
    before = len(harness.adjudicator.calls)
    harness.chat(message=message)
    calls = harness.adjudicator.calls[before:]
    return calls[0][1] if calls else Clearance.NONE


def screen_clearance(harness) -> Clearance:
    before = len(harness.adjudicator.calls)
    response = harness.client.post("/api/v1/screen", json={"message": "hello"})
    assert response.status_code == 200
    calls = harness.adjudicator.calls[before:]
    return calls[0][1] if calls else Clearance.NONE


@pytest.mark.spec("API-CLEAR-001")
def test_correct_passphrase_grants_a_session_cookie(harness, valid_passphrase: str) -> None:
    response = harness.grant(valid_passphrase)

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


@pytest.mark.spec("API-CLEAR-002")
def test_wrong_or_unconfigured_passphrase_is_refused_identically(make_harness) -> None:
    configured = make_harness()
    unconfigured = make_harness(secret=None)

    wrong = configured.grant("guess")
    unset = unconfigured.grant("guess")

    assert wrong.status_code == unset.status_code == 401
    assert wrong.json()["detail"] == unset.json()["detail"]
    assert set_cookie(wrong) == set_cookie(unset) == ""


@pytest.mark.spec("API-CLEAR-003")
def test_neither_passphrase_nor_token_is_persisted_or_logged(
    make_harness, valid_passphrase: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    db = tmp_path / "shield.db"
    harness = make_harness(sessions=SqliteSessionStore(db))

    harness.grant("wrong guess")
    token = harness.grant(valid_passphrase).cookies[COOKIE]
    harness.chat(message="hello")

    stored = b"".join(p.read_bytes() for p in tmp_path.iterdir() if p.is_file())
    for secret in (valid_passphrase, "wrong guess", token):
        assert secret.encode() not in stored
        assert secret not in caplog.text
        assert secret not in json.dumps(
            [r.model_dump(mode="json") for r in harness.audit_log._records]
        )
    with sqlite3.connect(db) as connection:
        hashes = [row[0] for row in connection.execute("select token_hash from sessions")]
    assert hashes == [hashlib.sha256(token.encode()).hexdigest()]


@pytest.mark.spec("API-CLEAR-004")
def test_live_session_grants_clearance_on_chat_and_screen(harness, valid_passphrase: str) -> None:
    harness.grant(valid_passphrase)

    assert clearance_seen(harness) is Clearance.GRANTED
    assert screen_clearance(harness) is Clearance.GRANTED


@pytest.mark.spec("API-CLEAR-004")
def test_missing_unknown_or_expired_cookie_means_no_clearance(harness) -> None:
    assert clearance_seen(harness) is Clearance.NONE
    assert screen_clearance(harness) is Clearance.NONE

    harness.client.cookies.set(COOKIE, "not-a-real-token")
    assert clearance_seen(harness) is Clearance.NONE

    expired, _ = asyncio.run(harness.sessions.create(timedelta(seconds=-1)))
    harness.client.cookies.set(COOKIE, expired)
    assert clearance_seen(harness) is Clearance.NONE
    assert screen_clearance(harness) is Clearance.NONE


@pytest.mark.spec("API-CLEAR-005")
def test_revoking_ends_the_session(harness, valid_passphrase: str) -> None:
    token = harness.grant(valid_passphrase).cookies[COOKIE]

    response = harness.client.delete("/api/v1/clearance")

    assert response.status_code == 204
    header = set_cookie(response).lower()
    assert header.startswith(f"{COOKIE}=")
    assert "max-age=0" in header or "expires=thu, 01 jan 1970" in header
    assert asyncio.run(harness.sessions.lookup(token)) is None
    harness.client.cookies.set(COOKIE, token)
    assert clearance_seen(harness) is Clearance.NONE


@pytest.mark.spec("API-CLEAR-005")
def test_revoking_without_a_session_is_a_no_op(harness) -> None:
    assert harness.client.delete("/api/v1/clearance").status_code == 204


@pytest.mark.spec("API-CLEAR-006")
def test_status_reports_the_live_session(harness, valid_passphrase: str) -> None:
    assert harness.client.get("/api/v1/clearance").json() == {"granted": False, "expires_at": None}

    granted = harness.grant(valid_passphrase).json()
    status = harness.client.get("/api/v1/clearance").json()

    assert status["granted"] is True
    assert datetime.fromisoformat(status["expires_at"]) == datetime.fromisoformat(
        granted["expires_at"]
    )


@pytest.mark.spec("API-CLEAR-007")
def test_sqlite_sessions_survive_a_restart_and_expired_rows_are_purged(tmp_path: Path) -> None:
    db = tmp_path / "shield.db"
    first = SqliteSessionStore(db)
    stale, _ = asyncio.run(first.create(timedelta(seconds=-1)))
    live, expires_at = asyncio.run(first.create(timedelta(hours=1)))

    reopened = SqliteSessionStore(db)

    assert asyncio.run(reopened.lookup(live)) == expires_at
    assert asyncio.run(reopened.lookup(stale)) is None
    with sqlite3.connect(db) as connection:
        (count,) = connection.execute("select count(*) from sessions").fetchone()
    assert count == 1


@pytest.mark.spec("API-CLEAR-008")
def test_repeated_failures_are_rate_limited(harness, valid_passphrase: str) -> None:
    limit = harness.container.settings.CLEARANCE_MAX_ATTEMPTS
    for _ in range(limit):
        assert harness.grant("guess").status_code == 401

    blocked = harness.grant(valid_passphrase)

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert set_cookie(blocked) == ""


@pytest.mark.spec("API-CLEAR-008")
def test_a_successful_grant_resets_the_failure_count(harness, valid_passphrase: str) -> None:
    limit = harness.container.settings.CLEARANCE_MAX_ATTEMPTS
    for _ in range(limit - 1):
        harness.grant("guess")
    assert harness.grant(valid_passphrase).status_code == 200

    for _ in range(limit - 1):
        assert harness.grant("guess").status_code == 401
    assert harness.grant("guess").status_code == 401


@pytest.mark.spec("API-CLEAR-008")
def test_the_limit_lifts_after_the_window(harness, valid_passphrase: str) -> None:
    for _ in range(harness.container.settings.CLEARANCE_MAX_ATTEMPTS):
        harness.grant("guess")

    harness.clock.advance(harness.container.settings.CLEARANCE_WINDOW_MINUTES * 60 + 1)

    assert harness.grant(valid_passphrase).status_code == 200


@pytest.mark.spec("API-CLEAR-009")
def test_requests_no_longer_carry_a_passphrase(harness) -> None:
    assert "passphrase" not in ChatRequest.model_fields
    assert "passphrase" not in ScreenRequest.model_fields

    harness.chat(message="hello")

    metadata = harness.audit_log._records[0].metadata
    assert metadata["clearance"] == "NONE"
    assert "passphrase_provided" not in metadata


@pytest.mark.spec("API-CLEAR-009")
def test_contract_publishes_clearance_and_drops_passphrase() -> None:
    contract = json.loads(render())
    schemas = contract["components"]["schemas"]

    assert {"get", "post", "delete"} <= set(contract["paths"]["/api/v1/clearance"])
    assert set(schemas["ClearanceStatus"]["properties"]) == {"granted", "expires_at"}
    assert "passphrase" not in schemas["ChatRequest"]["properties"]
    assert "passphrase" not in schemas["ScreenRequest"]["properties"]


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


@pytest.mark.spec("API-CLEAR-011")
def test_a_recent_failed_guess_means_denied_until_the_window_passes(harness) -> None:
    harness.grant("guess")

    assert clearance_seen(harness) is Clearance.DENIED
    assert screen_clearance(harness) is Clearance.DENIED

    harness.clock.advance(harness.container.settings.CLEARANCE_WINDOW_MINUTES * 60 + 1)

    assert clearance_seen(harness) is Clearance.NONE


@pytest.mark.spec("API-CLEAR-011")
def test_a_live_session_outranks_an_earlier_failed_guess(harness, valid_passphrase: str) -> None:
    harness.grant("guess")
    harness.grant(valid_passphrase)

    assert clearance_seen(harness) is Clearance.GRANTED
    assert harness.audit_log._records[0].metadata["clearance"] == "GRANTED"


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


@pytest.mark.spec("API-CLEAR-013")
def test_session_store_failure_fails_closed(make_harness, caplog: pytest.LogCaptureFixture) -> None:
    harness = make_harness(sessions=ExplodingSessions())
    harness.client.cookies.set(COOKIE, "some-token")

    events = harness.chat(message="hello")

    assert events[-1]["type"] == "FINAL_RESPONSE"
    assert harness.adjudicator.calls == []
    assert screen_clearance(harness) is Clearance.NONE
    assert any(r.exc_info and "disk full" in str(r.exc_info[1]) for r in caplog.records)
