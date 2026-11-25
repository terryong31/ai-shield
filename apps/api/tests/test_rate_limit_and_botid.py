"""Rate limiting, BotID proxy headers, and prod config guard (spec 0043)."""

from __future__ import annotations

import logging
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shield_api.container import ConfigurationError, Container, build_container
from shield_api.dependencies import client_address
from shield_api.main import create_app
from shield_api.services.admins import SupabaseAdminAuthenticator
from shield_api.services.clearance import Clearance
from shield_api.services.identity import SupabasePlayerIdentity
from shield_api.services.players import InMemoryPlayerStore
from shield_api.services.rate_limit import RateLimiter
from shield_api.services.scores import InMemoryScoreStore
from shield_api.services.sessions import AttemptLimiter, InMemorySessionStore
from shield_api.settings import Settings
from shield_engine import Verdict
from shield_engine.ports import ChatCompletion
from shield_engine.testing import ScriptedUsageChatModel, StaticClassifier

from .conftest import FakeAuthDirectory, FakeClient, FakeClock

SAFE_REPLY = ChatCompletion(
    text='{"reply": "Hello!", "tool_calls": [], "refused": false}',
    input_tokens=10,
    output_tokens=5,
)


class FakeAsyncRedis:
    """Minimal async Redis INCR/EXPIRE double with optional failure injection."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        if self.fail:
            raise RuntimeError("redis down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        if self.fail:
            raise RuntimeError("redis down")
        self.ttls[key] = seconds
        return True


def _prod_harness(
    *,
    app_env: Literal["development", "production"] = "production",
    trusted_ip_header: str | None = "x-shield-client-ip",
    trusted_proxy_secret: str | None = "s3cret",  # noqa: S107
    redis_client: Any = None,
    clock: FakeClock | None = None,
    confirm_email: bool = False,
) -> tuple[TestClient, Container, FakeAuthDirectory, FakeClock, RateLimiter]:
    clk = clock or FakeClock()
    auth = FakeAuthDirectory(confirm_email=confirm_email)
    auth.add("admin@example.com", "admin-pass", app_metadata={"provider": "email", "role": "admin"})
    settings = Settings(
        _env_file=None,
        APP_ENV=app_env,
        SESSION_COOKIE_SECURE=False,
        TRUSTED_CLIENT_IP_HEADER=trusted_ip_header,
        TRUSTED_PROXY_SECRET=SecretStr(trusted_proxy_secret) if trusted_proxy_secret else None,
        REDIS_URL=SecretStr("redis://localhost:6379/0") if app_env == "production" else None,
        MODEL_SIGNING_KEY=SecretStr("test-signing-key") if app_env == "production" else None,
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
            auth.client, redirect_to="http://localhost:3000/auth/confirmed"
        ),
        attempts=AttemptLimiter(max_attempts=5, clock=clk),
        rate_limiter=limiter,
    )
    client = TestClient(create_app(container))
    client.__enter__()
    return client, container, auth, clk, limiter


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


def _headers(
    ip: str = "198.51.100.1",
    secret: str = "s3cret",  # noqa: S107
    botid: str = "pass",
) -> dict[str, str]:
    return {
        "x-shield-client-ip": ip,
        "x-shield-proxy-secret": secret,
        "x-shield-botid": botid,
    }


@pytest.mark.spec("API-RATE-001")
def test_auth_ip_bucket_allows_30_across_auth_routes_and_limits_31st() -> None:
    client, _, auth, clk, _ = _prod_harness()
    with client:
        h = _headers("203.0.113.10")
        for i in range(30):
            if i % 4 == 0:
                r = client.post(
                    "/api/v1/auth/login",
                    json={"email": f"u{i}@x.com", "password": "Password1"},
                    headers=h,
                )
            elif i % 4 == 1:
                r = client.post(
                    "/api/v1/auth/register",
                    json={"email": f"r{i}@x.com", "password": "Password1"},
                    headers=h,
                )
            elif i % 4 == 2:
                r = client.post("/api/v1/auth/recover", json={"email": f"rec{i}@x.com"}, headers=h)
            else:
                r = client.post(
                    "/api/v1/auth/resend-confirmation", json={"email": f"res{i}@x.com"}, headers=h
                )
            assert r.status_code != 429

        blocked = client.post(
            "/api/v1/auth/register",
            json={"email": "over@x.com", "password": "Password1"},
            headers=h,
        )
        assert blocked.status_code == 429
        retry = int(blocked.headers["retry-after"])
        assert retry >= 1
        assert blocked.json()["detail"] == f"Too many requests. Try again in {retry} seconds."
        auth.calls.clear()
        blocked2 = client.post(
            "/api/v1/auth/login", json={"email": "over@x.com", "password": "Password1"}, headers=h
        )
        assert blocked2.status_code == 429
        assert auth.calls == []
        clk.advance(301)
        assert (
            client.post(
                "/api/v1/auth/recover", json={"email": "after@x.com"}, headers=h
            ).status_code
            == 200
        )


@pytest.mark.spec("API-RATE-002")
def test_anonymous_route_allows_30_per_hour_and_limits_31st_with_no_cookie() -> None:
    client, *_ = _prod_harness()
    with client:
        h = _headers("203.0.113.11")
        for _ in range(30):
            assert client.post("/api/v1/auth/anonymous", headers=h).status_code == 200
        blocked = client.post("/api/v1/auth/anonymous", headers=h)
        assert blocked.status_code == 429
        assert "shield_player_session" not in blocked.headers.get("set-cookie", "")


@pytest.mark.spec("API-RATE-003")
@pytest.mark.spec("API-RATE-004")
@pytest.mark.spec("API-RATE-005")
def test_failed_login_per_email_limits_after_10_resets_after_window_and_ignores_successes() -> None:
    client, _, auth, clk, _ = _prod_harness()
    with client:
        user = auth.add("ada@example.com", "StrongPass1")
        auth.confirm(user.email)

        # 9 failures from rotating IPs + 5 successes -> none limited (API-RATE-004)
        for i in range(9):
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "ada@example.com", "password": "WrongPass1"},
                headers=_headers(f"203.0.113.{i + 20}"),
            )
            assert res.status_code == 401
        for i in range(5):
            ok = client.post(
                "/api/v1/auth/login",
                json={"email": "ada@example.com", "password": "StrongPass1"},
                headers=_headers(f"203.0.113.{i + 40}"),
            )
            assert ok.status_code == 200

        # 10th failure fills bucket; 11th returns 429 without verifying (API-RATE-003)
        tenth = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "WrongPass1"},
            headers=_headers("203.0.113.99"),
        )
        assert tenth.status_code == 401
        auth.calls.clear()
        eleventh = client.post(
            "/api/v1/auth/login",
            json={"email": "Ada@Example.com", "password": "StrongPass1"},
            headers=_headers("203.0.113.100"),
        )
        assert eleventh.status_code == 429
        assert int(eleventh.headers["retry-after"]) >= 1
        assert auth.calls == []

        # Passing 15-minute window restores access (API-RATE-005)
        clk.advance(901)
        restored = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "StrongPass1"},
            headers=_headers("203.0.113.101"),
        )
        assert restored.status_code == 200


@pytest.mark.spec("API-RATE-006")
@pytest.mark.spec("API-RATE-007")
def test_recover_and_resend_limit_to_one_per_60s_per_email_identically() -> None:
    client, _, auth, clk, _ = _prod_harness()
    with client:
        auth.add("known@example.com", "StrongPass1")
        h1 = _headers("203.0.113.1")
        h2 = _headers("203.0.113.2")

        r1 = client.post("/api/v1/auth/recover", json={"email": "known@example.com"}, headers=h1)
        r2 = client.post("/api/v1/auth/recover", json={"email": "known@example.com"}, headers=h2)
        u1 = client.post("/api/v1/auth/recover", json={"email": "unknown@example.com"}, headers=h1)
        u2 = client.post("/api/v1/auth/recover", json={"email": "unknown@example.com"}, headers=h2)
        assert r1.status_code == u1.status_code == 200
        assert r1.json() == u1.json()
        assert r2.status_code == u2.status_code == 429
        assert r2.json() == u2.json()

        clk.advance(61)
        assert (
            client.post(
                "/api/v1/auth/recover", json={"email": "known@example.com"}, headers=h1
            ).status_code
            == 200
        )

        auth.calls.clear()
        s1 = client.post(
            "/api/v1/auth/resend-confirmation", json={"email": "known@example.com"}, headers=h1
        )
        s2 = client.post(
            "/api/v1/auth/resend-confirmation", json={"email": "known@example.com"}, headers=h2
        )
        assert s1.status_code == 202
        assert s2.status_code == 429
        assert auth.calls == ["resend"]


@pytest.mark.spec("API-RATE-008")
@pytest.mark.spec("API-RATE-009")
def test_game_run_limits_actor_at_10_and_ip_at_30_per_minute() -> None:
    client, container, *_ = _prod_harness()
    agent = ScriptedUsageChatModel(replies=[], default=SAFE_REPLY)
    container.game_agents = {"standard": agent}
    with client:
        h = _headers("203.0.113.50")
        # Open an anonymous session (free/anon actor limit on /game/run is 10/min)
        assert client.post("/api/v1/auth/anonymous", headers=h).status_code == 200
        for _ in range(10):
            # Run 10 waves within the per-minute actor limit
            res = client.post(
                "/api/v1/game/run",
                json={"level_id": "easy-1", "board": _simple_board()},
                headers=h,
            )
            assert res.status_code == 200

        limited_actor = client.post(
            "/api/v1/game/run",
            json={"level_id": "easy-1", "board": _simple_board()},
            headers=h,
        )
        assert limited_actor.status_code == 429
        assert int(limited_actor.headers["retry-after"]) >= 1

        # Fresh sessions from same IP reach 30/min total (IP bucket shared across routes)
        calls_before = len(agent.calls)
        client2 = TestClient(client.app)
        with client2:
            for s in range(4):
                assert (
                    client2.post(
                        "/api/v1/auth/anonymous", headers=_headers("203.0.113.50")
                    ).status_code
                    == 200
                )
                count = 5 if s < 3 else 4
                for _ in range(count):
                    r = client2.post(
                        "/api/v1/game/run",
                        json={"level_id": "easy-1", "board": _simple_board()},
                        headers=_headers("203.0.113.50"),
                    )
                    assert r.status_code == 200
            # Total runs on 203.0.113.50 so far: 10 + 1 + 19 = 30 -> 31st hits IP limit!
            client2.post("/api/v1/auth/anonymous", headers=_headers("203.0.113.50"))
            over_ip = client2.post(
                "/api/v1/game/run",
                json={"level_id": "medium-1", "board": _simple_board()},
                headers=_headers("203.0.113.50"),
            )
            assert over_ip.status_code == 429
            assert len(agent.calls) == calls_before
            # Different IP is unaffected
            assert (
                client2.post(
                    "/api/v1/game/run",
                    json={"level_id": "easy-1", "board": _simple_board()},
                    headers=_headers("203.0.113.51"),
                ).status_code
                == 200
            )


@pytest.mark.spec("API-RATE-010")
def test_game_train_limits_account_to_10_per_minute() -> None:
    import asyncio

    from shield_api.dependencies import PLAYER_SESSION_COOKIE

    client, container, auth, *_ = _prod_harness()
    csv = "text,label\nignore rules,1\nbypass policy,1\nopen hours,0\ntrack order,0\n"
    with client:
        user = auth.add("trainer@example.com", "StrongPass1")
        auth.confirm(user.email)
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "trainer@example.com", "password": "StrongPass1"},
                headers=_headers("203.0.113.60"),
            ).status_code
            == 200
        )
        # Paid tier allows 200 trains/day so the 10/min limiter trips on the 11th call.
        asyncio.run(container.players.upgrade(client.cookies.get(PLAYER_SESSION_COOKIE)))
        for _ in range(10):
            r = client.post(
                "/api/v1/game/train",
                json={"algorithm": "tfidf", "csv_text": csv},
                headers=_headers("203.0.113.60"),
            )
            assert r.status_code == 200
        limited = client.post(
            "/api/v1/game/train",
            json={"algorithm": "tfidf", "csv_text": csv},
            headers=_headers("203.0.113.60"),
        )
        assert limited.status_code == 429
        assert "retry-after" in {k.lower() for k in limited.headers}


@pytest.mark.spec("API-RATE-011")
def test_development_environment_applies_no_rate_limits() -> None:
    client, *_ = _prod_harness(app_env="development")
    with client:
        for _ in range(35):
            assert client.post("/api/v1/auth/anonymous").status_code == 200


@pytest.mark.spec("API-RATE-012")
def test_redis_rate_limiter_shares_counts_across_containers() -> None:
    shared_redis = FakeAsyncRedis()
    clk = FakeClock()
    c1, *_ = _prod_harness(redis_client=shared_redis, clock=clk)
    c2, *_ = _prod_harness(redis_client=shared_redis, clock=clk)
    h = _headers("203.0.113.70")
    with c1, c2:
        for i in range(15):
            assert (
                c1.post(
                    "/api/v1/auth/register",
                    json={"email": f"a{i}@x.com", "password": "Password1"},
                    headers=h,
                ).status_code
                == 200
            )
        for i in range(15):
            assert (
                c2.post(
                    "/api/v1/auth/register",
                    json={"email": f"b{i}@x.com", "password": "Password1"},
                    headers=h,
                ).status_code
                == 200
            )
        over = c1.post(
            "/api/v1/auth/register",
            json={"email": "over@x.com", "password": "Password1"},
            headers=h,
        )
        assert over.status_code == 429


@pytest.mark.spec("API-RATE-013")
def test_redis_failure_falls_back_to_local_limiter_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    failing_redis = FakeAsyncRedis(fail=True)
    client, *_ = _prod_harness(redis_client=failing_redis)
    h = _headers("203.0.113.71")
    with client:
        for _ in range(30):
            assert client.post("/api/v1/auth/anonymous", headers=h).status_code == 200
        blocked = client.post("/api/v1/auth/anonymous", headers=h)
        assert blocked.status_code == 429
    assert any(
        "rate" in rec.getMessage().lower() or "redis" in rec.getMessage().lower()
        for rec in caplog.records
        if rec.levelno == logging.WARNING
    )


@pytest.mark.spec("API-RATE-014")
def test_rate_limiter_hashes_keys_and_never_logs_raw_ip_or_email(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    redis_client = FakeAsyncRedis()
    client, _, _, _, limiter = _prod_harness(redis_client=redis_client)
    h = _headers("203.0.113.7")
    with client:
        client.post("/api/v1/auth/recover", json={"email": "ada@example.com"}, headers=h)
        client.post("/api/v1/auth/recover", json={"email": "ada@example.com"}, headers=h)

    all_keys = list(redis_client.counts.keys()) + [str(k) for k in limiter._counts]
    assert all_keys
    for raw in ("203.0.113.7", "ada@example.com"):
        assert all(raw not in k for k in all_keys)
        assert raw not in caplog.text


class _DummyApp:
    def __init__(self, settings: Settings) -> None:
        self.state = type("State", (), {"container": type("C", (), {"settings": settings})()})()


def _fake_request(
    headers: dict[str, str] | None = None,
    *,
    peer: str = "10.0.0.9",
    settings: Settings | None = None,
) -> Any:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw,
        "client": (peer, 12345),
        "app": _DummyApp(settings) if settings else None,
    }
    return Request(scope)


@pytest.mark.spec("API-IP-001")
def test_unset_trusted_header_ignores_forwarded_headers() -> None:
    s = Settings(_env_file=None, TRUSTED_CLIENT_IP_HEADER=None)
    req = _fake_request({"x-forwarded-for": "198.51.100.1"}, peer="127.0.0.5", settings=s)
    assert client_address(req, s) == "127.0.0.5"


@pytest.mark.spec("API-IP-002")
def test_trusted_header_without_secret_reads_first_ip_entry() -> None:
    s = Settings(
        _env_file=None, TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip", TRUSTED_PROXY_SECRET=None
    )
    req = _fake_request(
        {"x-shield-client-ip": "198.51.100.1, 10.0.0.1"}, peer="127.0.0.5", settings=s
    )
    assert client_address(req, s) == "198.51.100.1"


@pytest.mark.spec("API-IP-003")
def test_trusted_header_requires_matching_proxy_secret_when_set() -> None:
    s = Settings(
        _env_file=None,
        TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
        TRUSTED_PROXY_SECRET=SecretStr("s3cret"),
    )
    missing = _fake_request({"x-shield-client-ip": "198.51.100.1"}, peer="127.0.0.5", settings=s)
    wrong = _fake_request(
        {"x-shield-client-ip": "198.51.100.1", "x-shield-proxy-secret": "nope"},
        peer="127.0.0.5",
        settings=s,
    )
    good = _fake_request(
        {"x-shield-client-ip": "198.51.100.1", "x-shield-proxy-secret": "s3cret"},
        peer="127.0.0.5",
        settings=s,
    )
    assert client_address(missing, s) == "127.0.0.5"
    assert client_address(wrong, s) == "127.0.0.5"
    assert client_address(good, s) == "198.51.100.1"


@pytest.mark.spec("API-IP-004")
@pytest.mark.parametrize("bad", ["evil", "", "   ", "999.999.999.999"])
def test_malformed_trusted_ip_falls_back_to_peer(bad: str) -> None:
    s = Settings(_env_file=None, TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip")
    req = _fake_request({"x-shield-client-ip": bad}, peer="127.0.0.5", settings=s)
    assert client_address(req, s) == "127.0.0.5"


@pytest.mark.spec("API-IP-005")
def test_clearance_attempt_limiter_uses_trusted_client_ip_per_address() -> None:
    client, *_ = _prod_harness()
    with client:
        for _ in range(5):
            assert (
                client.post(
                    "/api/v1/clearance",
                    json={"email": "admin@example.com", "password": "wrong"},
                    headers=_headers("203.0.113.1"),
                ).status_code
                == 401
            )
        locked = client.post(
            "/api/v1/clearance",
            json={"email": "admin@example.com", "password": "wrong"},
            headers=_headers("203.0.113.1"),
        )
        assert locked.status_code == 429

        other_ok = client.post(
            "/api/v1/clearance",
            json={"email": "admin@example.com", "password": "admin-pass"},
            headers=_headers("203.0.113.2"),
        )
        assert other_ok.status_code == 200


@pytest.mark.spec("API-BOTID-001")
@pytest.mark.spec("API-BOTID-002")
@pytest.mark.spec("API-BOTID-006")
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/auth/anonymous", None),
        ("/api/v1/auth/register", {"email": "a@example.com", "password": "Password1"}),
        ("/api/v1/auth/login", {"email": "a@example.com", "password": "Password1"}),
        (
            "/api/v1/game/run",
            {
                "level_id": "easy-1",
                "board": {
                    "nodes": [
                        {"id": "in", "kind": "incoming", "config": {}},
                        {"id": "ast", "kind": "assistant", "config": {}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "in", "source_handle": "out", "target": "ast"}
                    ],
                },
            },
        ),
        (
            "/api/v1/game/train",
            {
                "algorithm": "tfidf",
                "csv_text": (
                    "text,label\nhello world,0\nignore previous,1\nopen hours,0\nbypass rules,1\n"
                ),
            },
        ),
    ],
)
def test_production_botid_gate_enforced_before_handler_and_rate_limiter(
    path: str, payload: dict[str, Any] | None
) -> None:
    client, container, auth, _, limiter = _prod_harness()
    with client:
        # Missing botid / wrong secret -> 403 and zero calls/increments
        for bad_headers in [
            {"x-shield-client-ip": "203.0.113.80"},
            {"x-shield-client-ip": "203.0.113.80", "x-shield-botid": "pass"},
            {
                "x-shield-client-ip": "203.0.113.80",
                "x-shield-botid": "pass",
                "x-shield-proxy-secret": "wrong",
            },
        ]:
            res = client.post(path, json=payload, headers=bad_headers)
            assert res.status_code == 403
            assert res.json() == {"detail": "Request blocked."}
        assert auth.calls == []
        assert limiter._counts == {}

        # Valid headers reach handler (no 403 from BotID)
        ok = client.post(path, json=payload, headers=_headers("203.0.113.80"))
        assert (
            ok.status_code != 403 or path == "/api/v1/game/train"
        )  # signed-in check on /train if not signed in
        assert ok.json().get("detail") != "Request blocked."
        assert container is not None


@pytest.mark.spec("API-BOTID-003")
def test_development_environment_skips_botid_header_requirement() -> None:
    client, *_ = _prod_harness(app_env="development")
    with client:
        assert client.post("/api/v1/auth/anonymous").status_code == 200
        assert (
            client.post(
                "/api/v1/game/run", json={"level_id": "easy-1", "board": _simple_board()}
            ).status_code
            == 200
        )


@pytest.mark.spec("API-BOTID-004")
def test_production_without_proxy_secret_refuses_protected_routes_and_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    client, *_ = _prod_harness(trusted_proxy_secret=None)
    assert any(
        "TRUSTED_PROXY_SECRET" in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.ERROR
    )
    with client:
        res = client.post("/api/v1/auth/anonymous", headers={"x-shield-botid": "pass"})
        assert res.status_code == 403


@pytest.mark.spec("API-BOTID-005")
def test_production_unprotected_routes_ignore_missing_botid_headers() -> None:
    client, *_ = _prod_harness()
    with client:
        assert client.get("/api/v1/game/levels").status_code == 200
        assert client.get("/api/v1/auth/session").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204


@pytest.mark.spec("API-PROD-002")
@pytest.mark.spec("API-PROD-006")
def test_production_build_container_requires_redis_and_supabase_together() -> None:
    with pytest.raises(ConfigurationError) as exc1:
        build_container(
            Settings(
                _env_file=None,
                APP_ENV="production",
                SUPABASE_URL="https://example.supabase.co",
                SUPABASE_KEY=SecretStr("service-key"),
                REDIS_URL=None,
                TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
                TRUSTED_PROXY_SECRET=SecretStr("s3cret"),
            )
        )
    assert "REDIS_URL" in str(exc1.value)

    with pytest.raises(ConfigurationError) as exc2:
        build_container(
            Settings(
                _env_file=None,
                APP_ENV="production",
                SUPABASE_URL="   ",
                SUPABASE_KEY=SecretStr("   "),
                REDIS_URL=SecretStr("   "),
                TRUSTED_CLIENT_IP_HEADER="   ",
                TRUSTED_PROXY_SECRET=SecretStr("   "),
            )
        )
    msg = str(exc2.value)
    assert "SUPABASE_URL" in msg
    assert "SUPABASE_KEY" in msg
    assert "REDIS_URL" in msg
    assert "TRUSTED_CLIENT_IP_HEADER" in msg
    assert "TRUSTED_PROXY_SECRET" in msg


@pytest.mark.spec("API-PROD-007")
def test_development_with_supabase_and_no_redis_uses_in_memory_limiter_and_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = FakeAuthDirectory()
    fake = FakeClient()
    fake.auth = auth.client().auth  # type: ignore[attr-defined]
    monkeypatch.setattr("supabase.create_client", lambda url, key: fake)

    container = build_container(
        Settings(
            _env_file=None,
            APP_ENV="development",
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
            REDIS_URL=None,
        )
    )
    assert container.rate_limiter._redis is None


@pytest.mark.spec("API-PROD-005")
def test_production_with_supabase_and_redis_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = FakeAuthDirectory()
    fake = FakeClient()
    fake.auth = auth.client().auth  # type: ignore[attr-defined]
    monkeypatch.setattr("supabase.create_client", lambda url, key: fake)
    fake_redis = FakeAsyncRedis()
    monkeypatch.setattr("redis.asyncio.from_url", lambda url, **kw: fake_redis)

    container = build_container(
        Settings(
            _env_file=None,
            APP_ENV="production",
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
            REDIS_URL=SecretStr("redis://localhost:6379/0"),
            TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
            TRUSTED_PROXY_SECRET=SecretStr("s3cret"),
        )
    )
    assert container.rate_limiter._redis is fake_redis
    assert Clearance.NONE is not None


@pytest.mark.spec("API-PROD-008")
def test_production_build_container_requires_trusted_ip_header_and_proxy_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeClient()
    monkeypatch.setattr("supabase.create_client", lambda url, key: fake)
    monkeypatch.setattr("redis.asyncio.from_url", lambda url, **kw: FakeAsyncRedis())

    for overrides, expected_missing in [
        ({"TRUSTED_PROXY_SECRET": SecretStr("s3cret")}, ("TRUSTED_CLIENT_IP_HEADER",)),
        ({"TRUSTED_CLIENT_IP_HEADER": "x-shield-client-ip"}, ("TRUSTED_PROXY_SECRET",)),
        (
            {"TRUSTED_CLIENT_IP_HEADER": "  ", "TRUSTED_PROXY_SECRET": SecretStr("  ")},
            ("TRUSTED_CLIENT_IP_HEADER", "TRUSTED_PROXY_SECRET"),
        ),
    ]:
        with pytest.raises(ConfigurationError) as exc:
            build_container(
                Settings(
                    _env_file=None,
                    APP_ENV="production",
                    SUPABASE_URL="https://example.supabase.co",
                    SUPABASE_KEY=SecretStr("service-key"),
                    REDIS_URL=SecretStr("redis://localhost:6379/0"),
                    **overrides,
                )
            )
        for name in expected_missing:
            assert name in str(exc.value)

    dev = build_container(
        Settings(
            _env_file=None,
            APP_ENV="development",
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
        )
    )
    assert dev.settings.TRUSTED_CLIENT_IP_HEADER is None
