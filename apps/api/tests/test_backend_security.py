"""Backend security hardening (spec 0054)."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from shield_api import schemas
from shield_api.container import ConfigurationError, build_container, resolve_model_signing_key
from shield_api.dependencies import client_address
from shield_api.services.auth_flows import AuthFlowRecord
from shield_api.services.spend import OwnerLocks
from shield_api.services.train_worker import worker_environment
from shield_api.settings import Settings

from .conftest import ADMIN_EMAIL, Harness
from .test_game_api import _valid_board_payload

REPO = Path(__file__).resolve().parents[3]
SECRET = "s" * 40
PLAYER_COOKIE = "shield_player_session"
PASSWORD = "Str0ngPassw0rd"
PROXY = {"x-shield-proxy-secret": SECRET, "x-shield-botid": "pass", "sec-fetch-site": "same-origin"}


def _production(harness: Harness, **overrides: Any) -> Harness:
    values: dict[str, Any] = {
        "_env_file": None,
        "APP_ENV": "production",
        "SESSION_COOKIE_SECURE": False,
        "TRUSTED_PROXY_SECRET": SECRET,
        "TRUSTED_CLIENT_IP_HEADER": "x-shield-client-ip",
    }
    values.update(overrides)
    harness.container.settings = Settings(**values)
    return harness


def _request(headers: dict[str, str], peer: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 1234),
    }
    return Request(scope)


def _sign_in(harness: Harness, email: str = "ada@example.com") -> str:
    harness.auth.add(email, PASSWORD)
    res = harness.client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200
    return res.cookies[PLAYER_COOKIE]


@pytest.mark.spec("API-SEC-001")
def test_validation_errors_never_echo_the_input(harness: Harness) -> None:
    secret = "weakpw1"
    cases = [
        ("/api/v1/auth/register", {"email": "ada@example.com", "password": secret}),
        ("/api/v1/auth/login", {"email": "ada@example.com", "password": secret}),
        ("/api/v1/auth/account/password", {"current_password": "", "new_password": secret}),
        ("/api/v1/clearance", {"email": ADMIN_EMAIL, "password": ""}),
    ]
    for path, body in cases:
        res = harness.client.post(path, json=body)
        assert res.status_code == 422, path
        text = res.text
        assert '"input"' not in text, path
        assert secret not in text, path


@pytest.mark.spec("API-SEC-002")
def test_client_address_trusts_only_the_signed_proxy_and_its_rightmost_hop() -> None:
    header = "x-shield-client-ip"
    chain = {header: "198.51.100.1, 203.0.113.9"}
    no_secret = Settings(_env_file=None, TRUSTED_CLIENT_IP_HEADER=header)
    assert client_address(_request(chain), no_secret) == "10.0.0.1"

    signed = Settings(_env_file=None, TRUSTED_CLIENT_IP_HEADER=header, TRUSTED_PROXY_SECRET=SECRET)
    wrong = {**chain, "x-shield-proxy-secret": "nope"}
    assert client_address(_request(wrong), signed) == "10.0.0.1"
    right = {**chain, "x-shield-proxy-secret": SECRET}
    assert client_address(_request(right), signed) == "203.0.113.9"
    bad_ip = {header: "203.0.113.9, not-an-ip", "x-shield-proxy-secret": SECRET}
    assert client_address(_request(bad_ip), signed) == "10.0.0.1"


@pytest.mark.spec("API-SEC-003")
def test_confirm_and_reset_password_are_rate_limited_per_ip(harness: Harness) -> None:
    _production(harness)
    # Both routes share the auth IP bucket with sign-in, so each uses its own address.
    for ip, path, body in [
        ("203.0.113.10", "/api/v1/auth/confirm", {"token_hash": "x", "type": "signup"}),
        (
            "203.0.113.11",
            "/api/v1/auth/reset-password",
            {"token_hash": "x", "new_password": PASSWORD},
        ),
    ]:
        headers = {**PROXY, "x-shield-client-ip": ip}
        statuses = [
            harness.client.post(path, json=body, headers=headers).status_code for _ in range(31)
        ]
        assert statuses[-1] == 429, path
        assert 429 not in statuses[:30], path


@pytest.mark.spec("API-SEC-003")
def test_register_is_rate_limited_per_email(harness: Harness) -> None:
    _production(harness)
    body = {"email": "new@example.com", "password": PASSWORD}
    harness.client.post("/api/v1/auth/register", json=body, headers=PROXY)
    other_ip = {**PROXY, "x-shield-client-ip": "203.0.113.50"}
    again = harness.client.post("/api/v1/auth/register", json=body, headers=other_ip)
    assert again.status_code == 429


@pytest.mark.spec("API-SEC-003")
def test_clearance_needs_botid_and_is_limited_per_email(harness: Harness) -> None:
    _production(harness)
    bare = {k: v for k, v in PROXY.items() if k != "x-shield-botid"}
    blocked = harness.client.post(
        "/api/v1/clearance", json={"email": ADMIN_EMAIL, "password": "wrong"}, headers=bare
    )
    assert blocked.status_code == 403

    limit = harness.container.settings.CLEARANCE_MAX_ATTEMPTS
    statuses = []
    for n in range(limit + 1):
        headers = {**PROXY, "x-shield-client-ip": f"203.0.113.{n + 1}"}
        res = harness.client.post(
            "/api/v1/clearance", json={"email": ADMIN_EMAIL, "password": "wrong"}, headers=headers
        )
        statuses.append(res.status_code)
    assert statuses[-1] == 429


@pytest.mark.spec("API-SEC-003")
def test_valid_login_resets_the_email_failure_counter(harness: Harness) -> None:
    _production(harness)
    harness.auth.add("ada@example.com", PASSWORD)

    def attempt(password: str, n: int) -> int:
        headers = {**PROXY, "x-shield-client-ip": f"198.51.100.{n}"}
        return harness.client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": password},
            headers=headers,
        ).status_code

    for n in range(9):
        assert attempt("WrongPassw0rd", n + 1) == 401
    assert attempt(PASSWORD, 50) == 200
    for n in range(9):
        assert attempt("WrongPassw0rd", n + 100) == 401
    assert attempt(PASSWORD, 200) == 200


def _chunks(size: int) -> Iterator[bytes]:
    sent = 0
    while sent < size:
        step = min(65536, size - sent)
        sent += step
        yield b" " * step


@pytest.mark.spec("API-SEC-004")
def test_streamed_bodies_over_the_route_limit_are_413(harness: Harness) -> None:
    big = harness.client.post(
        "/api/v1/game/run",
        content=_chunks(262_145),
        headers={"content-type": "application/json"},
    )
    assert big.status_code == 413
    train = harness.client.post(
        "/api/v1/game/train",
        content=_chunks(1_310_721),
        headers={"content-type": "application/json"},
    )
    assert train.status_code == 413
    within = harness.client.post(
        "/api/v1/game/train",
        content=_chunks(300_000),
        headers={"content-type": "application/json"},
    )
    assert within.status_code != 413


@pytest.mark.spec("API-SEC-004")
def test_node_config_is_bounded(harness: Harness) -> None:
    def run_with(config: dict[str, Any]) -> int:
        board = _valid_board_payload()
        board["nodes"][1]["config"] = config
        return harness.client.post(
            "/api/v1/game/run", json={"level_id": "easy-1", "board": board}
        ).status_code

    assert run_with({f"k{i}": 1 for i in range(33)}) == 422
    deep: dict[str, Any] = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    assert run_with(deep) == 422
    assert run_with({"keywords": ["x" * 17_000]}) == 422


@pytest.mark.spec("API-SEC-005")
def test_every_response_has_security_headers(harness: Harness) -> None:
    res = harness.client.get("/api/v1/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "strict-transport-security" not in res.headers

    _production(harness)
    prod = harness.client.get("/api/v1/health")
    assert prod.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


@pytest.mark.spec("API-SEC-005")
def test_private_routes_are_not_cached(harness: Harness) -> None:
    _sign_in(harness)
    for method, path in [
        ("GET", "/api/v1/game/saves/easy-1"),
        ("GET", "/api/v1/game/progress"),
        ("POST", "/api/v1/billing/sync"),
    ]:
        res = harness.client.request(method, path, headers={"sec-fetch-site": "same-origin"})
        assert res.headers.get("cache-control") == "private, no-store", path


@pytest.mark.spec("API-SEC-006")
def test_cross_site_state_changes_are_blocked(harness: Harness) -> None:
    body = {"level_id": "easy-1", "board": _valid_board_payload()}
    for headers in [
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
        {"origin": "https://evil.example"},
    ]:
        res = harness.client.post("/api/v1/game/run", json=body, headers=headers)
        assert res.status_code == 403, headers
        assert res.json() == {"detail": "Cross-site request blocked."}

    webhook = harness.client.post(
        "/api/v1/billing/webhook", content=b"{}", headers={"sec-fetch-site": "cross-site"}
    )
    assert webhook.json() != {"detail": "Cross-site request blocked."}

    _production(harness)
    harness.client.cookies.set(PLAYER_COOKIE, "some-token")
    bare = {k: v for k, v in PROXY.items() if k != "sec-fetch-site"}
    unlabelled = harness.client.post("/api/v1/game/run", json=body, headers=bare)
    assert unlabelled.status_code == 403


@pytest.mark.spec("API-SEC-006")
def test_a_proxied_preview_origin_is_allowed(harness: Harness) -> None:
    # The web proxy already checked that Origin is its own page (WEB-SEC-006), so a
    # request that proves the proxy secret may come from any deployment of the site.
    _production(harness)
    body = {"level_id": "easy-1", "board": _valid_board_payload()}
    preview = {**PROXY, "origin": "https://ai-shield-git-feat-x.vercel.app"}
    res = harness.client.post("/api/v1/game/run", json=body, headers=preview)
    assert res.json() != {"detail": "Cross-site request blocked."}

    unproxied = harness.client.post(
        "/api/v1/game/run", json=body, headers={"origin": "https://evil.example"}
    )
    assert unproxied.status_code == 403


@pytest.mark.spec("API-SEC-006")
def test_admin_cookie_is_samesite_strict(harness: Harness, admin_password: str) -> None:
    res = harness.grant(admin_password)
    assert res.status_code == 200
    assert "samesite=strict" in res.headers["set-cookie"].lower()


@pytest.mark.spec("API-SEC-007")
def test_confirm_without_anything_to_verify_is_400(harness: Harness) -> None:
    res = harness.client.post(
        "/api/v1/auth/confirm",
        json={"code": "abc", "type": "signup", "confirm": True, "flow_id": "missing"},
    )
    assert res.status_code == 400


@pytest.mark.spec("API-SEC-007")
def test_confirm_with_a_wrong_purpose_flow_is_400(harness: Harness) -> None:
    flow_id = asyncio.run(
        harness.container.auth_flows.create(
            AuthFlowRecord(purpose="recovery", browser_hash=None, code_verifier="v"),
            ttl_seconds=600,
        )
    )
    res = harness.client.post(
        "/api/v1/auth/confirm",
        json={"code": "abc", "type": "signup", "confirm": True, "flow_id": flow_id},
    )
    assert res.status_code == 400


@pytest.mark.spec("API-SEC-007")
def test_reset_password_ignores_a_flow_of_another_purpose(harness: Harness) -> None:
    seen: list[str | None] = []

    async def record(**kwargs: Any) -> str:
        seen.append(kwargs.get("code_verifier"))
        return "ada@example.com"

    harness.container.identity.complete_password_reset = record  # type: ignore[method-assign]
    flow_id = asyncio.run(
        harness.container.auth_flows.create(
            AuthFlowRecord(purpose="signup", browser_hash=None, code_verifier="leaked"),
            ttl_seconds=600,
        )
    )
    harness.client.post(
        "/api/v1/auth/reset-password",
        json={"code": "abc", "flow_id": flow_id, "new_password": PASSWORD},
    )
    assert seen == [None]


@pytest.mark.spec("API-SEC-008")
def test_train_worker_gets_only_allowlisted_environment() -> None:
    parent = {
        "PATH": "/usr/bin",
        "HOME": "/home/app",
        "SUPABASE_KEY": "secret",
        "STRIPE_SECRET_KEY": "sk_live_x",
        "GOOGLE_API_KEY": "g",
    }
    assert worker_environment(parent) == {"PATH": "/usr/bin", "HOME": "/home/app"}

    from shield_api.services import train_worker

    source = inspect.getsource(train_worker.TrainWorkerRunner._ensure_started)
    assert "env=worker_environment(" in source


@pytest.mark.spec("API-SEC-008")
def test_short_signing_keys_are_rejected_in_production() -> None:
    short = Settings(_env_file=None, APP_ENV="production", MODEL_SIGNING_KEY="too-short")
    assert resolve_model_signing_key(short) is None
    strong = Settings(_env_file=None, APP_ENV="production", MODEL_SIGNING_KEY="k" * 32)
    assert resolve_model_signing_key(strong) == b"k" * 32


@pytest.mark.spec("API-SEC-009")
def test_request_models_reject_unknown_fields(harness: Harness) -> None:
    node = {"id": "n", "kind": "word_filter", "config": {}}
    edge = {"id": "e", "source": "a", "source_handle": "out", "target": "b"}
    cases: list[tuple[Any, dict[str, Any]]] = [
        (schemas.ClearanceRequest, {"email": ADMIN_EMAIL, "password": "x"}),
        (schemas.PlayerRegisterRequest, {"email": "a@example.com", "password": PASSWORD}),
        (schemas.PlayerLoginRequest, {"email": "a@example.com", "password": PASSWORD}),
        (schemas.PlayerResendRequest, {"email": "a@example.com"}),
        (schemas.PlayerRecoverRequest, {"email": "a@example.com"}),
        (schemas.GameRunRequest, {"board": {"nodes": [], "edges": []}}),
        (schemas.BoardNodeSchema, node),
        (schemas.BoardEdgeSchema, edge),
        (schemas.BoardGraphSchema, {"nodes": [], "edges": []}),
        (schemas.AgentToolSchema, {"name": "t", "description": "d", "allowed": True}),
    ]
    for model, body in cases:
        model.model_validate(body)
        with pytest.raises(ValidationError):
            model.model_validate({**body, "unexpected": 1})

    res = harness.client.post(
        "/api/v1/game/run",
        json={"level_id": "easy-1", "board": _valid_board_payload(), "unexpected": 1},
    )
    assert res.status_code == 422


@pytest.mark.spec("API-SEC-010")
def test_password_change_rotates_the_session(harness: Harness) -> None:
    old = _sign_in(harness)
    res = harness.client.post(
        "/api/v1/auth/account/password",
        json={"current_password": PASSWORD, "new_password": "N3wStr0ngPassw0rd"},
    )
    assert res.status_code == 200
    new = res.cookies.get(PLAYER_COOKIE)
    assert new
    assert new != old
    assert asyncio.run(harness.container.players.lookup(old)).authenticated is False
    assert asyncio.run(harness.container.players.lookup(new)).authenticated is True


@pytest.mark.spec("API-SEC-010")
def test_upgrade_rotates_the_session(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(allow_self_upgrade=True)
    old = _sign_in(harness)
    res = harness.client.post("/api/v1/auth/upgrade")
    assert res.status_code == 200
    new = res.cookies.get(PLAYER_COOKIE)
    assert new
    assert new != old
    assert asyncio.run(harness.container.players.lookup(old)).authenticated is False
    assert asyncio.run(harness.container.players.lookup(new)).tier == "paid"


@pytest.mark.spec("API-SEC-011")
def test_runs_of_one_spend_owner_are_serialized() -> None:
    locks = OwnerLocks()
    order: list[str] = []

    async def run(name: str, owner: str) -> None:
        async with locks.hold(owner):
            order.append(f"{name}:start")
            await asyncio.sleep(0.01)
            order.append(f"{name}:end")

    async def main() -> None:
        await asyncio.gather(run("a", "ada"), run("b", "ada"), run("c", "grace"))

    asyncio.run(main())
    ada = [step for step in order if step[0] in "ab"]
    assert ada in (
        ["a:start", "a:end", "b:start", "b:end"],
        ["b:start", "b:end", "a:start", "a:end"],
    )

    from shield_api.routers import game

    assert "container.spend_locks.hold(spend_owner)" in inspect.getsource(game)


@pytest.mark.spec("API-SEC-012")
def test_production_refuses_insecure_configuration() -> None:
    base: dict[str, Any] = {
        "_env_file": None,
        "APP_ENV": "production",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_KEY": "service-role-key",
        "WEB_BASE_URL": "https://ai-shield.example",
        "SESSION_COOKIE_SECURE": True,
        "ALLOW_SELF_UPGRADE": False,
        "REDIS_URL": "rediss://cache.example:6379",
        "TRUSTED_PROXY_SECRET": SECRET,
        "TRUSTED_CLIENT_IP_HEADER": "x-shield-client-ip",
        "MODEL_SIGNING_KEY": "k" * 32,
    }
    assert build_container(Settings(**base)).settings.APP_ENV == "production"
    for override in [
        {"WEB_BASE_URL": "http://ai-shield.example"},
        {"SESSION_COOKIE_SECURE": False},
        {"ALLOW_SELF_UPGRADE": True},
        {"REDIS_URL": "redis://cache.example:6379"},
    ]:
        with pytest.raises(ConfigurationError):
            build_container(Settings(**{**base, **override}))


@pytest.mark.spec("API-SEC-012")
def test_admin_actions_are_audited_without_credentials(
    harness: Harness, admin_password: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="shield_api.audit")
    harness.client.post("/api/v1/clearance", json={"email": ADMIN_EMAIL, "password": "wrong"})
    harness.grant(admin_password)
    harness.client.delete("/api/v1/game/scores")
    events = [json.loads(r.getMessage()) for r in caplog.records if r.name == "shield_api.audit"]
    names = [e["event"] for e in events]
    assert "clearance.denied" in names
    assert "clearance.granted" in names
    assert "scores.cleared" in names
    assert admin_password not in caplog.text
    assert ADMIN_EMAIL not in caplog.text

    dockerfile = (REPO / "apps" / "api" / "Dockerfile").read_text()
    assert "--no-server-header" in dockerfile


@pytest.mark.spec("API-SEC-013")
def test_production_requires_the_proxy_secret_everywhere(harness: Harness) -> None:
    _production(harness)
    for method, path in [
        ("GET", "/api/v1/game/scores"),
        ("GET", "/api/v1/game/levels"),
        ("POST", "/api/v1/clearance"),
        ("PUT", "/api/v1/game/saves/easy-1"),
    ]:
        for headers in [
            {"sec-fetch-site": "same-origin"},
            {"x-shield-proxy-secret": "wrong", "sec-fetch-site": "same-origin"},
        ]:
            res = harness.client.request(method, path, json={}, headers=headers)
            assert res.status_code == 403, (method, path)
            assert res.json() == {"detail": "Request blocked."}
    assert harness.client.get("/api/v1/health").status_code == 200
    webhook = harness.client.post("/api/v1/billing/webhook", content=b"{}")
    assert webhook.json() != {"detail": "Request blocked."}
    assert harness.client.get("/api/v1/game/levels", headers=PROXY).status_code == 200


@pytest.mark.spec("API-SEC-014")
def test_supabase_and_compose_are_hardened() -> None:
    config = (REPO / "supabase" / "config.toml").read_text()
    assert "auto_expose_new_tables = false" in config
    assert "minimum_password_length = 8" in config
    assert 'password_requirements = "lower_upper_letters_digits"' in config
    compose = (REPO / "compose.yaml").read_text()
    assert "127.0.0.1:6379:6379" in compose
    assert '"6379:6379"' not in compose
    assert "- 6379:6379" not in compose
