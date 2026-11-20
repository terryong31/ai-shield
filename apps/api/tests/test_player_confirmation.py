"""Player email confirmation through Supabase Auth (spec 0027)."""

import asyncio
import json
import logging
import sqlite3
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from shield_api.openapi import render
from shield_api.services.players import (
    InMemoryPlayerStore,
    PlayerStore,
    SqlitePlayerStore,
    SupabasePlayerStore,
)
from shield_api.services.sqlite import connect_domains

from .conftest import FakeClient, Harness

COOKIE = "shield_player_session"
PASSWORD = "StrongPass1"
CONFIRMED = {"status": "confirmation_sent"}
NOT_CONFIRMED = "Confirm your email before signing in."
REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "contracts" / "shield-api.openapi.json"
MIGRATIONS = REPO / "supabase" / "migrations"


def register(harness: Harness, email: str, password: str = PASSWORD, name: str | None = "Ada"):
    body: dict[str, Any] = {"email": email, "password": password}
    if name is not None:
        body["player_name"] = name
    return harness.client.post("/api/v1/auth/register", json=body)


def login(harness: Harness, email: str, password: str = PASSWORD):
    return harness.client.post("/api/v1/auth/login", json={"email": email, "password": password})


def resend(harness: Harness, email: str):
    return harness.client.post("/api/v1/auth/resend-confirmation", json={"email": email})


def set_cookie(response) -> str:
    return response.headers.get("set-cookie", "")


def redirect_to(harness: Harness) -> str:
    return f"{harness.container.settings.WEB_BASE_URL}/auth/confirmed"


@pytest.mark.spec("API-VERIFY-001")
def test_register_sends_a_confirmation_email_and_signs_nobody_in(
    make_harness: Callable[..., Harness],
) -> None:
    supabase = make_harness(supabase_players=True)
    response = register(supabase, "new@example.com")

    assert response.status_code == 202
    assert response.json() == CONFIRMED
    assert set_cookie(response) == ""
    assert supabase.auth.sign_ups == [
        {
            "email": "new@example.com",
            "password": PASSWORD,
            "options": {
                "data": {"player_name": "Ada"},
                "email_redirect_to": redirect_to(supabase),
            },
        }
    ]
    session = supabase.client.get("/api/v1/auth/session").json()
    assert session["authenticated"] is False
    store = supabase.container.players
    assert isinstance(store, InMemoryPlayerStore)
    assert all(account.password_hash is None for account in store._accounts.values())


@pytest.mark.spec("API-VERIFY-002")
def test_register_answers_every_email_the_same(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(supabase_players=True)
    first = register(harness, "new@example.com")
    unconfirmed = register(harness, "new@example.com")
    harness.auth.confirm("new@example.com")
    confirmed = register(harness, "new@example.com")
    down = make_harness(supabase_players=True)
    down.auth.fail = True
    failed = register(down, "other@example.com")

    for response in (unconfirmed, confirmed, failed):
        assert response.status_code == first.status_code == 202
        assert response.content == first.content
        assert set_cookie(response) == ""


@pytest.mark.spec("API-VERIFY-003")
def test_login_needs_a_confirmed_email(make_harness: Callable[..., Harness]) -> None:
    supabase = make_harness(supabase_players=True)
    register(supabase, "new@example.com")

    unconfirmed = login(supabase, "new@example.com")
    wrong = login(supabase, "new@example.com", "wrong password")
    unknown = login(supabase, "nobody@example.com")

    assert unconfirmed.status_code == 403
    assert unconfirmed.json() == {"detail": NOT_CONFIRMED}
    assert set_cookie(unconfirmed) == ""
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert set_cookie(wrong) == set_cookie(unknown) == ""


def _stores(tmp_path: Path, fake_client: FakeClient) -> dict[str, PlayerStore]:
    return {
        "memory": InMemoryPlayerStore(),
        "sqlite": SqlitePlayerStore(tmp_path / "shield.db"),
        "supabase": SupabasePlayerStore(fake_client),
    }


def _profile(store: PlayerStore, email: str) -> dict[str, Any] | None:
    if isinstance(store, InMemoryPlayerStore):
        account = store._accounts.get(email)
        return None if account is None else vars(account)
    if isinstance(store, SqlitePlayerStore):
        rows = store._run("select * from players.accounts where email = ?", (email,))
        return dict(rows[0]) if rows else None
    assert isinstance(store, SupabasePlayerStore)
    return store._account(email)


@pytest.mark.spec("API-VERIFY-004")
@pytest.mark.parametrize("kind", ["memory", "sqlite", "supabase"])
def test_first_login_creates_a_free_profile_and_keeps_existing_ones(
    make_harness: Callable[..., Harness], tmp_path: Path, fake_supabase, kind: str
) -> None:
    store = _stores(tmp_path, fake_supabase())[kind]
    harness = make_harness(supabase_players=True, players=store)
    register(harness, "ada@example.com", name="Ada")
    register(harness, "grace@example.com", name=None)
    harness.auth.confirm("ada@example.com")
    harness.auth.confirm("grace@example.com")

    assert login(harness, "ada@example.com").json()["player_name"] == "Ada"
    harness.client.post("/api/v1/auth/upgrade")
    assert login(harness, "grace@example.com").json()["player_name"] == "grace"

    ada = _profile(store, "ada@example.com")
    grace = _profile(store, "grace@example.com")
    assert ada is not None
    assert grace is not None
    assert (ada["tier"], ada["password_hash"]) == ("paid", None)
    assert (grace["tier"], grace["password_hash"]) == ("free", None)

    again = login(harness, "ada@example.com").json()
    assert (again["player_name"], again["tier"]) == ("Ada", "paid")


@pytest.mark.spec("API-VERIFY-010")
def test_login_opens_a_gateway_session_and_signs_supabase_out(
    make_harness: Callable[..., Harness],
) -> None:
    supabase = make_harness(supabase_players=True)
    register(supabase, "ada@example.com")
    supabase.auth.confirm("ada@example.com")

    response = login(supabase, "ada@example.com")

    assert response.status_code == 200
    body = response.json()
    assert (body["authenticated"], body["is_anonymous"]) == (True, False)
    assert body["email"] == "ada@example.com"
    assert set_cookie(response).startswith(f"{COOKIE}=")
    assert supabase.client.get("/api/v1/auth/session").json()["email"] == "ada@example.com"
    assert supabase.auth.open_sessions == 0


@pytest.mark.spec("API-VERIFY-011")
def test_supabase_failures_never_fall_back_to_a_local_password(
    make_harness: Callable[..., Harness],
) -> None:
    legacy_store = InMemoryPlayerStore()
    asyncio.run(
        legacy_store.register(
            email="old@example.com",
            password="LegacyPass1",
            player_name="Old",
            ttl=timedelta(hours=1),
        )
    )
    harness = make_harness(supabase_players=True, players=legacy_store)
    harness.auth.add("old@example.com", "SupabasePass1")

    assert login(harness, "old@example.com", "LegacyPass1").status_code == 401
    assert login(harness, "old@example.com", "SupabasePass1").status_code == 200

    harness.client.cookies.clear()
    harness.auth.fail = True
    down = login(harness, "old@example.com", "LegacyPass1")
    assert down.status_code == 503
    assert set_cookie(down) == ""


@pytest.mark.spec("API-VERIFY-012")
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("register", {"email": "not-an-email", "password": PASSWORD}),
        ("register", {"email": "a@b", "password": PASSWORD}),
        ("register", {"email": "two words@example.com", "password": PASSWORD}),
        ("register", {"email": "ada@example.com", "password": "12345"}),
        ("register", {"email": "ada@example.com", "password": "x" * 513}),
        ("login", {"email": "not-an-email", "password": PASSWORD}),
        ("login", {"email": "ada@example.com", "password": ""}),
        ("resend-confirmation", {"email": "not-an-email"}),
        ("resend-confirmation", {"email": "x" * 250 + "@example.com"}),
    ],
)
def test_invalid_input_is_rejected_before_supabase(
    make_harness: Callable[..., Harness], path: str, body: dict[str, str]
) -> None:
    supabase = make_harness(supabase_players=True)
    response = supabase.client.post(f"/api/v1/auth/{path}", json=body)

    assert response.status_code == 422
    assert supabase.auth.calls == []


@pytest.mark.spec("API-VERIFY-013")
def test_the_contract_documents_the_confirmation_flow() -> None:
    committed = CONTRACT.read_text(encoding="utf-8")
    assert json.loads(render()) == json.loads(committed)
    contract = json.loads(committed)
    paths = contract["paths"]
    schemas = contract["components"]["schemas"]

    resend_op = paths["/api/v1/auth/resend-confirmation"]["post"]
    request_ref = resend_op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/PlayerResendRequest")
    accepted = resend_op["responses"]["202"]["content"]["application/json"]["schema"]["$ref"]
    assert accepted.endswith("/PlayerConfirmationResponse")
    assert set(schemas["PlayerResendRequest"]["properties"]) == {"email"}
    assert set(schemas["PlayerConfirmationResponse"]["properties"]) == {"status"}

    assert {"200", "202"} <= set(paths["/api/v1/auth/register"]["post"]["responses"])
    assert {"401", "403", "503"} <= set(paths["/api/v1/auth/login"]["post"]["responses"])


@pytest.mark.spec("API-VERIFY-005")
def test_resend_answers_every_email_the_same(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(supabase_players=True)
    register(harness, "new@example.com")
    known = resend(harness, "new@example.com")
    unknown = resend(harness, "nobody@example.com")
    down = make_harness(supabase_players=True)
    down.auth.fail = True
    failed = resend(down, "new@example.com")

    for response in (known, unknown, failed):
        assert response.status_code == 202
        assert response.json() == CONFIRMED
        assert response.content == known.content
    assert harness.auth.resends == [
        {
            "type": "signup",
            "email": email,
            "options": {"email_redirect_to": redirect_to(harness)},
        }
        for email in ("new@example.com", "nobody@example.com")
    ]


@pytest.mark.spec("API-VERIFY-006")
def test_without_confirmation_in_the_project_register_signs_in(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(supabase_players=True)
    harness.auth.confirm_email = False

    response = register(harness, "ada@example.com")

    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"
    assert set_cookie(response).startswith(f"{COOKIE}=")
    assert harness.auth.open_sessions == 0


@pytest.mark.spec("API-VERIFY-007")
def test_local_mode_keeps_immediate_sign_in(harness: Harness) -> None:
    created = register(harness, "ada@example.com")
    taken = register(harness, "ada@example.com")
    bad = login(harness, "ada@example.com", "wrong password")
    harness.client.cookies.clear()
    good = login(harness, "ada@example.com")
    resent = resend(harness, "ada@example.com")

    assert created.status_code == 200
    assert set_cookie(created).startswith(f"{COOKIE}=")
    assert taken.status_code == 409
    assert bad.status_code == 401
    assert good.status_code == 200
    assert resent.status_code == 202
    assert resent.json() == CONFIRMED
    assert harness.auth.calls == []


@pytest.mark.spec("API-VERIFY-008")
def test_only_the_named_supabase_calls_are_made(make_harness: Callable[..., Harness]) -> None:
    supabase = make_harness(supabase_players=True)
    calls = supabase.auth.calls

    supabase.client.post("/api/v1/auth/anonymous")
    assert calls == []

    register(supabase, "ada@example.com")
    assert calls == ["sign_up"]

    calls.clear()
    supabase.auth.confirm("ada@example.com")
    login(supabase, "ada@example.com")
    assert calls == ["sign_in_with_password", "sign_out"]

    calls.clear()
    login(supabase, "ada@example.com", "wrong password")
    assert calls == ["sign_in_with_password"]

    calls.clear()
    resend(supabase, "ada@example.com")
    assert calls == ["resend"]

    calls.clear()
    supabase.auth.confirm_email = False
    register(supabase, "grace@example.com")
    assert calls == ["sign_up", "sign_out"]


@pytest.mark.spec("API-VERIFY-014")
def test_passwords_stay_out_of_logs_and_files(
    make_harness: Callable[..., Harness], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = make_harness(supabase_players=True, players=SqlitePlayerStore(tmp_path / "shield.db"))

    register(harness, "ada@example.com")
    harness.auth.confirm("ada@example.com")
    login(harness, "ada@example.com", "a wrong password")
    login(harness, "ada@example.com")
    resend(harness, "ada@example.com")

    stored = b"".join(p.read_bytes() for p in tmp_path.iterdir() if p.is_file())
    for secret in (PASSWORD, "a wrong password"):
        assert secret.encode() not in stored
        assert secret not in caplog.text


@pytest.mark.spec("API-VERIFY-009")
def test_password_columns_are_nullable_in_postgres_and_sqlite(tmp_path: Path) -> None:
    sql = "\n".join(p.read_text(encoding="utf-8").lower() for p in sorted(MIGRATIONS.glob("*.sql")))
    assert "alter column password_hash drop not null" in sql
    assert "alter column salt drop not null" in sql

    # A database created before spec 0027 (NOT NULL columns) is migrated in place.
    legacy = tmp_path / "legacy.db"
    SqlitePlayerStore(legacy)
    with connect_domains(legacy) as connection:
        connection.executescript(
            """
            drop table players.accounts;
            create table players.accounts (
              email text primary key, password_hash text not null, salt text not null,
              player_name text not null, tier text not null default 'free',
              created_at text not null
            );
            insert into players.accounts values ('old@example.com', 'h', 's', 'Old', 'paid', 'x');
            """
        )

    for path in (tmp_path / "fresh.db", legacy):
        SqlitePlayerStore(path)
        with connect_domains(path) as connection:
            connection.row_factory = sqlite3.Row
            columns = {
                row["name"]: row["notnull"]
                for row in connection.execute("pragma players.table_info(accounts)")
            }
        assert columns["password_hash"] == 0
        assert columns["salt"] == 0

    with connect_domains(legacy) as connection:
        assert connection.execute(
            "select player_name, tier from players.accounts where email = 'old@example.com'"
        ).fetchone() == ("Old", "paid")


@pytest.mark.spec("API-AUTH-001")
def test_register_and_login_enforce_password_strength_and_length(harness: Harness) -> None:
    for weak in ("Short1A", "alllowercase1", "ALLUPPERCASE1", "NoNumbersHere"):
        bad_reg = harness.client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": weak, "player_name": "Ada"},
        )
        assert bad_reg.status_code == 422, weak

    good_reg = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "ValidPass1", "player_name": "Ada"},
    )
    assert good_reg.status_code == 200

    bad_email_login = harness.client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "ValidPass1"},
    )
    assert bad_email_login.status_code == 422

    short_pw_login = harness.client.post(
        "/api/v1/auth/login",
        json={"email": "new@example.com", "password": "Short1A"},
    )
    assert short_pw_login.status_code == 422
