"""Stripe pass checkout (spec 0049). No network: Stripe is replaced at the port."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from shield_api.container import ConfigurationError, build_container
from shield_api.services.billing import StripePayments
from shield_api.services.players import (
    InMemoryPlayerStore,
    PurchasePendingError,
    SupabasePlayerStore,
)
from shield_api.settings import Settings

from .conftest import FakeClient, Harness
from .test_account_settings import change_email, delete_account, login, register, session

CHECKOUT = "/api/v1/billing/checkout"
WEBHOOK = "/api/v1/billing/webhook"
HOOK_KEY = "whsec_unit"
API_KEY = "sk_test_unit"
MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
DAY = timedelta(days=1)


class FakeStripe:
    """In-memory Stripe: Checkout Sessions, expiry and refunds."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.params: list[dict[str, Any]] = []
        self.refunds: list[dict[str, str]] = []
        self.calls: list[str] = []
        self.fail = False

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail:
            raise ConnectionError("stripe down")

    def create(self, params: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        self._call("create")
        self.params.append({**params, "idempotency_key": idempotency_key})
        session_id = f"cs_{len(self.sessions) + 1}"
        self.sessions[session_id] = {
            "id": session_id,
            "url": f"https://checkout.stripe.test/{session_id}",
            "status": "open",
            "payment_status": "unpaid",
            "mode": "payment",
            "amount_total": params["line_items"][0]["price_data"]["unit_amount"],
            "currency": "usd",
            "payment_intent": None,
            "expires_at": params["expires_at"],
        }
        return self.sessions[session_id]

    def retrieve(self, session_id: str) -> dict[str, Any] | None:
        self._call("retrieve")
        return self.sessions.get(session_id)

    def expire(self, session_id: str) -> bool:
        self._call("expire")
        session = self.sessions.get(session_id)
        if session is None or session["status"] != "open":
            return False
        session["status"] = "expired"
        return True

    def refund(self, payment_intent: str, idempotency_key: str) -> None:
        self._call("refund")
        entry = {"payment_intent": payment_intent, "key": idempotency_key}
        if entry not in self.refunds:
            self.refunds.append(entry)

    def pay(self, session_id: str | None = None) -> None:
        """The player paid on the Stripe page; no webhook was sent."""
        session = self.sessions[session_id or list(self.sessions)[-1]]
        session.update(status="complete", payment_status="paid", payment_intent="pi_1", url=None)


@pytest.fixture
def stripe() -> FakeStripe:
    return FakeStripe()


@pytest.fixture
def shop(harness: Harness, stripe: FakeStripe) -> Harness:
    harness.container.payments = StripePayments(API_KEY, HOOK_KEY, api=stripe)
    return harness


def buy(harness: Harness, stripe: FakeStripe) -> str:
    res = harness.client.post(CHECKOUT)
    assert res.status_code == 200, res.text
    return str(stripe.params[-1]["client_reference_id"])


def store_of(harness: Harness) -> InMemoryPlayerStore:
    players = harness.container.players
    assert isinstance(players, InMemoryPlayerStore)
    return players


def age_passes(harness: Harness, days: int) -> None:
    """Move every pass into the past, as if ``days`` had gone by."""
    players = store_of(harness)
    for account in players._accounts.values():
        if account.paid_until:
            account.paid_until -= days * DAY
    for purchase in players._purchases.values():
        if purchase.starts_at and purchase.ends_at:
            purchase.starts_at -= days * DAY
            purchase.ends_at -= days * DAY


def sync(harness: Harness, *, cancel: bool = False) -> Any:
    return harness.client.post("/api/v1/billing/sync", json={"cancel": cancel})


def sign(payload: bytes, secret: str = HOOK_KEY, at: int | None = None) -> str:
    stamp = int(time.time()) if at is None else at
    digest = hmac.new(
        secret.encode(), str(stamp).encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    return f"t={stamp},v1={digest}"


def post_event(harness: Harness, event: dict[str, Any], signature: str | None = None) -> Any:
    payload = json.dumps(event).encode()
    return harness.client.post(
        WEBHOOK,
        content=payload,
        headers={"stripe-signature": sign(payload) if signature is None else signature},
    )


def paid_event(purchase_id: str, kind: str = "checkout.session.completed", **over: Any) -> Any:
    obj = {
        "client_reference_id": purchase_id,
        "mode": "payment",
        "payment_status": "paid",
        "amount_total": 500,
        "currency": "usd",
        "payment_intent": "pi_1",
    }
    livemode = over.pop("livemode", False)
    return {"id": "evt_1", "type": kind, "livemode": livemode, "data": {"object": obj | over}}


def refund_event(purchase_id: str, *, refunded: bool = True) -> Any:
    return {
        "id": "evt_2",
        "type": "charge.refunded",
        "livemode": False,
        "data": {"object": {"refunded": refunded, "metadata": {"purchase_id": purchase_id}}},
    }


def paid_until(harness: Harness) -> datetime | None:
    raw = session(harness.client)["paid_until"]
    return datetime.fromisoformat(raw) if raw else None


def days_left(harness: Harness) -> int:
    until = paid_until(harness)
    assert until is not None
    return round((until - datetime.now(UTC)) / DAY)


@pytest.mark.spec("API-BILL-001")
def test_checkout_uses_server_price_and_urls_and_returns_the_stripe_url(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")

    res = shop.client.post(CHECKOUT, json={"price": 1, "email": "x@example.com"})

    assert res.status_code == 200
    assert res.json() == {"url": "https://checkout.stripe.test/cs_1"}
    params = stripe.params[0]
    assert params["mode"] == "payment"
    price = params["line_items"][0]["price_data"]
    assert (price["currency"], price["unit_amount"]) == ("usd", 500)
    base = shop.container.settings.WEB_BASE_URL
    assert params["success_url"] == f"{base}/plans?checkout=success"
    assert params["cancel_url"] == f"{base}/plans?checkout=cancelled"
    assert params["customer_email"] == "ada@example.com"
    purchase_id = params["client_reference_id"]
    assert params["payment_intent_data"]["metadata"] == {"purchase_id": purchase_id}
    assert params["idempotency_key"] == purchase_id
    players = shop.container.players
    assert isinstance(players, InMemoryPlayerStore)
    assert players._purchases[purchase_id].status == "pending"
    assert shop.client.get("/api/v1/game/levels").json()["billing_enabled"] is True


@pytest.mark.spec("API-BILL-002")
def test_checkout_refuses_anonymous_players_and_reports_outages(
    shop: Harness, stripe: FakeStripe
) -> None:
    assert shop.client.post(CHECKOUT).status_code == 403
    shop.client.post("/api/v1/auth/anonymous")
    assert shop.client.post(CHECKOUT).status_code == 403
    assert stripe.params == []

    register(shop.client, "ada@example.com")
    stripe.fail = True
    assert shop.client.post(CHECKOUT).status_code == 503
    players = shop.container.players
    assert isinstance(players, InMemoryPlayerStore)
    assert all(p.status == "expired" for p in players._purchases.values())

    shop.container.payments = None
    assert shop.client.post(CHECKOUT).status_code == 503
    assert shop.client.post(WEBHOOK, content=b"{}").status_code == 503
    assert shop.client.get("/api/v1/game/levels").json()["billing_enabled"] is False


@pytest.mark.spec("API-BILL-003")
def test_webhook_refuses_missing_wrong_and_old_signatures(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    event = paid_event(buy(shop, stripe))
    payload = json.dumps(event).encode()

    assert shop.client.post(WEBHOOK, content=payload).status_code == 400
    for signature in (
        "",
        "nonsense",
        sign(payload, secret="whsec_other"),
        sign(payload, at=int(time.time()) - 3600),
        sign(payload + b" "),
    ):
        assert post_event(shop, event, signature).status_code == 400
    assert session(shop.client)["tier"] == "free"


@pytest.mark.spec("API-BILL-003")
def test_webhook_refuses_signed_bodies_that_are_not_events(shop: Harness) -> None:
    for payload in (b"not json", b"[]", b'{"type": "checkout.session.completed"}'):
        res = shop.client.post(
            WEBHOOK, content=payload, headers={"stripe-signature": sign(payload)}
        )
        assert res.status_code == 400


@pytest.mark.spec("API-BILL-004")
@pytest.mark.parametrize(
    "kind", ["checkout.session.completed", "checkout.session.async_payment_succeeded"]
)
def test_paid_event_grants_thirty_days_once(shop: Harness, stripe: FakeStripe, kind: str) -> None:
    register(shop.client, "ada@example.com")
    event = paid_event(buy(shop, stripe), kind)

    assert post_event(shop, event).status_code == 200
    first = paid_until(shop)
    assert post_event(shop, event).status_code == 200

    assert days_left(shop) == 30
    assert paid_until(shop) == first
    status = session(shop.client)
    assert (status["tier"], status["daily_wave_limit"]) == ("paid", 300)


@pytest.mark.spec("API-BILL-004")
def test_second_purchase_extends_the_pass(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    for _ in range(2):
        assert post_event(shop, paid_event(buy(shop, stripe))).status_code == 200
    assert days_left(shop) == 60


@pytest.mark.spec("API-BILL-004")
def test_migration_fulfils_under_a_row_lock_and_denies_public_access() -> None:
    sql = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql"))).lower()
    assert "create table if not exists players.purchases" in sql
    assert "alter table players.purchases enable row level security" in sql
    assert "revoke all on table players.purchases from public, anon, authenticated" in sql
    body = sql[sql.rindex("create or replace function players.fulfil_purchase") :]
    assert "for update" in body[: body.index("$$;")]
    for name in (
        "fulfil_purchase(uuid, text, integer, text, integer)",
        "revoke_purchase(uuid, text, text)",
        "restore_purchase(text, text)",
    ):
        assert f"revoke all on function players.{name}" in sql
        assert f"grant execute on function players.{name}" in sql


@pytest.mark.spec("API-BILL-004")
async def test_supabase_store_fulfils_and_refunds_through_the_rpc(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    client = fake_supabase()
    store = SupabasePlayerStore(client)
    purchase_id = await store.create_purchase(
        "ada@example.com", amount_cents=500, currency="usd", livemode=False
    )
    row = client.schema("players").table("purchases").rows[0]
    assert (row["id"], row["email"], row["status"]) == (purchase_id, "ada@example.com", "pending")

    client.rpc_results["fulfil_purchase"] = "fulfilled"
    client.rpc_results["revoke_purchase"] = "revoked"
    client.rpc_results["restore_purchase"] = "restored"
    outcome = await store.fulfil_purchase(
        purchase_id, payment_intent="pi_1", amount_cents=500, currency="usd", days=30
    )
    assert outcome == "fulfilled"
    revoked = await store.revoke_purchase(
        purchase_id=purchase_id, payment_intent=None, status="refunded"
    )
    assert revoked == "revoked"
    assert await store.restore_purchase("pi_1", status="refunded") == "restored"

    await store.attach_session(purchase_id, "cs_1")
    pending = await store.pending_purchase("ada@example.com", livemode=False)
    assert pending is not None
    assert (pending.id, pending.session_id) == (purchase_id, "cs_1")
    assert await store.pending_purchase("ada@example.com", livemode=True) is None
    await store.expire_purchase(purchase_id)
    assert await store.pending_purchase("ada@example.com", livemode=False) is None


@pytest.mark.spec("API-BILL-005")
@pytest.mark.parametrize(
    "over",
    [
        {"payment_status": "unpaid"},
        {"amount_total": 1},
        {"currency": "idr"},
        {"mode": "subscription"},
        {"livemode": True},
        {"client_reference_id": str(uuid.uuid4())},
        {"client_reference_id": "not-a-uuid"},
        {"client_reference_id": None},
    ],
)
def test_events_that_do_not_match_a_purchase_grant_nothing(
    shop: Harness, stripe: FakeStripe, over: dict[str, Any]
) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)

    assert post_event(shop, paid_event(purchase_id, **over)).status_code == 200
    assert post_event(shop, paid_event(purchase_id, kind="customer.created")).status_code == 200

    assert session(shop.client)["tier"] == "free"
    assert paid_until(shop) is None


@pytest.mark.spec("API-BILL-006")
def test_expired_pass_is_free_without_a_new_sign_in(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    post_event(shop, paid_event(buy(shop, stripe)))
    assert shop.client.get("/api/v1/game/saves/custom").status_code != 403
    players = shop.container.players
    assert isinstance(players, InMemoryPlayerStore)
    players._accounts["ada@example.com"].paid_until = datetime.now(UTC) - timedelta(seconds=1)

    status = session(shop.client)

    assert (status["tier"], status["daily_wave_limit"]) == ("free", 5)
    assert shop.client.get("/api/v1/game/saves/custom").status_code == 403
    assert login(shop.client, "ada@example.com").json()["tier"] == "free"


@pytest.mark.spec("API-BILL-006")
@pytest.mark.parametrize(
    ("tier", "offset", "expected"),
    [("free", 1, "paid"), ("free", -1, "free"), ("paid", -1, "paid"), ("free", None, "free")],
)
async def test_supabase_tier_comes_from_the_grant_or_the_pass(
    fake_supabase: Callable[..., FakeClient], tier: str, offset: int | None, expected: str
) -> None:
    client = fake_supabase()
    until = None if offset is None else (datetime.now(UTC) + offset * DAY).isoformat()
    client.schema("players").table("accounts").rows = [
        {"email": "ada@example.com", "player_name": "Ada", "tier": tier, "paid_until": until}
    ]
    store = SupabasePlayerStore(client)

    token, status = await store.sign_in_verified(
        email="ada@example.com", player_name=None, ttl=timedelta(hours=1)
    )

    assert status.tier == expected
    assert (await store.lookup(token)).tier == expected


@pytest.mark.spec("API-BILL-007")
def test_full_refund_removes_the_days_once(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    first = buy(shop, stripe)
    post_event(shop, paid_event(first))
    post_event(shop, paid_event(buy(shop, stripe), payment_intent="pi_2"))

    assert post_event(shop, refund_event(first, refunded=False)).status_code == 200
    assert days_left(shop) == 60
    for _ in range(2):
        assert post_event(shop, refund_event(first)).status_code == 200
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-007")
def test_refund_before_the_paid_event_leaves_nothing_to_grant(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)

    post_event(shop, refund_event(purchase_id))
    post_event(shop, paid_event(purchase_id))

    assert session(shop.client)["tier"] == "free"


@pytest.mark.spec("API-BILL-008")
@pytest.mark.parametrize(
    ("key", "hook", "named"),
    [
        ("pk_test_secretvalue", HOOK_KEY, "STRIPE_SECRET_KEY"),
        ("sk_test_secretvalue", None, "STRIPE_WEBHOOK_SECRET"),
        ("sk_test_secretvalue", "  ", "STRIPE_WEBHOOK_SECRET"),
    ],
)
def test_bad_stripe_configuration_stops_startup_without_the_value(
    monkeypatch: pytest.MonkeyPatch, key: str, hook: str | None, named: str
) -> None:
    monkeypatch.setattr("supabase.create_client", lambda url, k: FakeClient())
    with pytest.raises(ConfigurationError) as exc:
        build_container(_settings(key, hook))
    assert named in str(exc.value)
    assert "secretvalue" not in str(exc.value)


@pytest.mark.spec("API-BILL-008")
@pytest.mark.parametrize(
    ("key", "livemode"),
    [("sk_test_a", False), ("rk_test_a", False), ("sk_live_a", True), ("rk_live_a", True)],
)
def test_sandbox_and_live_keys_configure_billing(
    monkeypatch: pytest.MonkeyPatch, key: str, livemode: bool
) -> None:
    monkeypatch.setattr("supabase.create_client", lambda url, k: FakeClient())
    payments = build_container(_settings(key, HOOK_KEY)).payments
    assert payments is not None
    assert payments.livemode is livemode
    assert build_container(_settings(None, None)).payments is None


def _settings(key: str | None, hook: str | None) -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV="development",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_KEY=SecretStr("service-key"),
        STRIPE_SECRET_KEY=SecretStr(key) if key else None,
        STRIPE_WEBHOOK_SECRET=SecretStr(hook) if hook else None,
    )


@pytest.mark.spec("API-BILL-009")
def test_pass_and_pending_purchase_follow_an_email_change(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    post_event(shop, paid_event(buy(shop, stripe)))
    pending = buy(shop, stripe)
    assert change_email(shop.client, "new@example.com").status_code == 202
    shop.auth.confirm_email_change("new@example.com")
    login(shop.client, "new@example.com")

    assert post_event(shop, paid_event(pending)).status_code == 200

    assert days_left(shop) == 60


@pytest.mark.spec("API-BILL-009")
def test_deletion_removes_the_email_from_purchases(
    shop: Harness, stripe: FakeStripe, caplog: pytest.LogCaptureFixture
) -> None:
    register(shop.client, "ada@example.com")
    done = buy(shop, stripe)
    post_event(shop, paid_event(done))
    buy(shop, stripe)
    assert delete_account(shop.client).status_code == 204
    caplog.clear()

    assert post_event(shop, refund_event(done)).status_code == 200

    assert "ada@example.com" not in caplog.text
    assert all(p.email is None for p in store_of(shop)._purchases.values())
    register(shop.client, "ada@example.com")
    assert session(shop.client)["tier"] == "free"


@pytest.mark.spec("API-BILL-009")
async def test_supabase_moves_and_clears_purchases(
    fake_supabase: Callable[..., FakeClient],
) -> None:
    client = fake_supabase()
    table = client.schema("players").table("purchases")
    table.rows = [
        {"id": "1", "email": "old@example.com", "status": "paid"},
        {"id": "2", "email": "old@example.com", "status": "pending"},
    ]
    store = SupabasePlayerStore(client)

    await store.move_email("old@example.com", "new@example.com")
    assert {r["email"] for r in table.rows} == {"new@example.com"}
    await store.delete_account("new@example.com")
    assert table.rows == [
        {"id": "1", "email": None, "status": "paid"},
        {"id": "2", "email": None, "status": "expired"},
    ]


@pytest.mark.spec("API-BILL-010")
def test_store_error_in_the_webhook_is_a_503_so_stripe_retries(
    shop: Harness, stripe: FakeStripe, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(shop.client, "ada@example.com")
    event = paid_event(buy(shop, stripe))

    async def broken(*_: Any, **__: Any) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(InMemoryPlayerStore, "fulfil_purchase", broken)
    assert post_event(shop, event).status_code == 503
    monkeypatch.undo()
    assert post_event(shop, event).status_code == 200
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-010")
def test_purchase_whose_account_is_moving_is_retried(
    shop: Harness, stripe: FakeStripe, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(shop.client, "ada@example.com")
    event = paid_event(buy(shop, stripe))
    players = shop.container.players
    assert isinstance(players, InMemoryPlayerStore)
    purchase = next(iter(players._purchases.values()))
    purchase.email = "moving@example.com"

    assert post_event(shop, event).status_code == 503
    purchase.email = "ada@example.com"
    assert post_event(shop, event).status_code == 200
    assert asyncio.run(players.email_taken("ada@example.com"))
    assert days_left(shop) == 30


# --- edge cases ----------------------------------------------------------------


def event(kind: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {"id": "evt_x", "type": kind, "livemode": False, "data": {"object": obj}}


@pytest.mark.spec("API-BILL-011")
def test_session_expires_soon_and_takes_only_cards_in_usd(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    buy(shop, stripe)
    params = stripe.params[0]
    assert 1800 < params["expires_at"] - time.time() <= 2100
    # Stripe refuses payment_method_types since its 2026-09-30 API version.
    assert "payment_method_types" not in params
    assert params["allowed_payment_method_types"] == ["card"]
    assert params["adaptive_pricing"] == {"enabled": False}


@pytest.mark.spec("API-BILL-012")
def test_second_checkout_reuses_the_open_session(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    first = shop.client.post(CHECKOUT).json()
    assert shop.client.post(CHECKOUT).json() == first
    assert len(stripe.sessions) == 1


@pytest.mark.spec("API-BILL-012")
def test_session_about_to_expire_is_replaced(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    buy(shop, stripe)
    stripe.sessions["cs_1"]["expires_at"] = int(time.time()) + 30
    buy(shop, stripe)
    assert [x["status"] for x in stripe.sessions.values()] == ["expired", "open"]


@pytest.mark.spec("API-BILL-012")
def test_concurrent_checkout_is_a_409(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    asyncio.run(
        store_of(shop).create_purchase(
            "ada@example.com", amount_cents=500, currency="usd", livemode=False
        )
    )
    assert shop.client.post(CHECKOUT).status_code == 409
    assert stripe.sessions == {}


@pytest.mark.spec("API-BILL-012")
def test_checkout_abandoned_before_its_session_does_not_block_forever(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    players = store_of(shop)
    old = asyncio.run(
        players.create_purchase("ada@example.com", amount_cents=500, currency="usd", livemode=False)
    )
    players._purchases[old].created_at -= timedelta(minutes=5)
    buy(shop, stripe)
    assert players._purchases[old].status == "expired"


@pytest.mark.spec("API-BILL-012")
async def test_supabase_unique_violation_is_a_pending_error(
    fake_supabase: Callable[..., FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Duplicate(Exception):
        code = "23505"

    client = fake_supabase()
    table = client.schema("players").table("purchases")

    def refuse(_row: dict[str, Any]) -> Any:
        raise Duplicate

    monkeypatch.setattr(table, "insert", refuse)
    with pytest.raises(PurchasePendingError):
        await SupabasePlayerStore(client).create_purchase(
            "ada@example.com", amount_cents=500, currency="usd", livemode=False
        )


@pytest.mark.spec("API-BILL-013")
def test_cancel_expires_the_open_session(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)

    res = sync(shop, cancel=True)

    assert (res.status_code, res.json()["state"]) == (200, "none")
    assert stripe.sessions["cs_1"]["status"] == "expired"
    assert store_of(shop)._purchases[purchase_id].status == "expired"


@pytest.mark.spec("API-BILL-013")
def test_cancel_after_paying_grants_the_pass(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    stripe.pay()

    body = sync(shop, cancel=True).json()
    post_event(shop, paid_event(purchase_id))

    assert (body["state"], body["session"]["tier"]) == ("paid", "paid")
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-013")
def test_sync_without_cancel_keeps_an_open_session(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    assert sync(shop).json()["state"] == "none"
    buy(shop, stripe)
    assert sync(shop).json()["state"] == "open"
    assert stripe.sessions["cs_1"]["status"] == "open"
    shop.client.cookies.clear()
    assert sync(shop).status_code == 403


@pytest.mark.spec("API-BILL-014")
def test_missed_webhook_is_repaired_by_sync(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    stripe.pay()

    assert sync(shop).json()["state"] == "paid"
    assert sync(shop).json()["state"] == "none"
    post_event(shop, paid_event(purchase_id))

    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-014")
def test_missed_webhook_is_repaired_by_the_next_checkout(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    buy(shop, stripe)
    stripe.pay()

    assert shop.client.post(CHECKOUT).status_code == 409

    assert len(stripe.sessions) == 1
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-014")
def test_payment_still_processing_does_not_open_a_second_session(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    buy(shop, stripe)
    stripe.sessions["cs_1"]["status"] = "complete"
    assert sync(shop).json()["state"] == "processing"
    assert shop.client.post(CHECKOUT).status_code == 409
    assert len(stripe.sessions) == 1


@pytest.mark.spec("API-BILL-015")
@pytest.mark.parametrize(
    "kind", ["checkout.session.expired", "checkout.session.async_payment_failed"]
)
def test_expired_session_closes_the_purchase_but_a_late_payment_still_counts(
    shop: Harness, stripe: FakeStripe, kind: str
) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)

    ended = paid_event(purchase_id, kind, payment_status="unpaid")
    assert post_event(shop, ended).status_code == 200
    assert store_of(shop)._purchases[purchase_id].status == "expired"
    post_event(shop, paid_event(purchase_id))
    assert days_left(shop) == 30
    post_event(shop, ended)
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-016")
def test_deleting_the_account_expires_the_open_session(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    buy(shop, stripe)
    assert delete_account(shop.client).status_code == 204
    assert stripe.sessions["cs_1"]["status"] == "expired"


@pytest.mark.spec("API-BILL-016")
def test_payment_for_a_deleted_account_is_refunded_once(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    stripe.pay()
    assert delete_account(shop.client).status_code == 204

    stripe.fail = True
    assert post_event(shop, paid_event(purchase_id)).status_code == 503
    stripe.fail = False
    for _ in range(2):
        assert post_event(shop, paid_event(purchase_id)).status_code == 200

    assert stripe.refunds == [{"payment_intent": "pi_1", "key": f"refund-{purchase_id}"}]
    assert store_of(shop)._purchases[purchase_id].status == "refunded"


@pytest.mark.spec("API-BILL-017")
def test_price_change_while_a_session_is_open_still_grants(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    store_of(shop)._purchases[purchase_id].amount_cents = 300
    post_event(shop, paid_event(purchase_id, amount_total=300))
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-017")
def test_paid_event_that_does_not_match_is_logged_as_an_error(
    shop: Harness, stripe: FakeStripe, caplog: pytest.LogCaptureFixture
) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    post_event(shop, paid_event(purchase_id, amount_total=1))
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any(purchase_id in message for message in errors)
    assert "ada@example.com" not in caplog.text


@pytest.mark.spec("API-BILL-018")
def test_refund_of_an_expired_pass_keeps_the_newer_pass(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    old = buy(shop, stripe)
    post_event(shop, paid_event(old))
    age_passes(shop, 40)
    post_event(shop, paid_event(buy(shop, stripe), payment_intent="pi_2"))

    post_event(shop, refund_event(old))

    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-018")
def test_refund_of_the_current_pass_removes_only_unused_days(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    first = buy(shop, stripe)
    post_event(shop, paid_event(first))
    second = buy(shop, stripe)
    post_event(shop, paid_event(second, payment_intent="pi_2"))
    age_passes(shop, 20)

    post_event(shop, refund_event(first))
    assert days_left(shop) == 30
    post_event(shop, refund_event(second))
    assert session(shop.client)["tier"] == "free"


@pytest.mark.spec("API-BILL-019")
@pytest.mark.parametrize(
    ("kind", "status"),
    [("refund.failed", "failed"), ("refund.updated", "failed"), ("refund.updated", "canceled")],
)
def test_failed_refund_gives_the_days_back_once(
    shop: Harness, stripe: FakeStripe, kind: str, status: str
) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    post_event(shop, paid_event(purchase_id))
    post_event(shop, refund_event(purchase_id))
    assert session(shop.client)["tier"] == "free"

    post_event(shop, event("refund.updated", {"payment_intent": "pi_1", "status": "succeeded"}))
    assert session(shop.client)["tier"] == "free"
    for _ in range(2):
        post_event(shop, event(kind, {"payment_intent": "pi_1", "status": status}))

    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-020")
def test_chargeback_removes_the_days_and_a_win_returns_them(
    shop: Harness, stripe: FakeStripe
) -> None:
    register(shop.client, "ada@example.com")
    post_event(shop, paid_event(buy(shop, stripe)))
    dispute = {"payment_intent": "pi_1", "status": "needs_response"}

    post_event(shop, event("charge.dispute.created", dispute))
    assert days_left(shop) == 30
    for _ in range(2):
        post_event(shop, event("charge.dispute.funds_withdrawn", dispute))
    assert session(shop.client)["tier"] == "free"
    for _ in range(2):
        post_event(shop, event("charge.dispute.funds_reinstated", dispute))
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-020")
def test_refund_after_a_chargeback_removes_nothing_more(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    post_event(shop, paid_event(purchase_id))
    post_event(shop, paid_event(buy(shop, stripe), payment_intent="pi_2"))
    dispute = {"payment_intent": "pi_1", "status": "lost"}
    post_event(shop, event("charge.dispute.funds_withdrawn", dispute))
    post_event(shop, refund_event(purchase_id))
    post_event(shop, event("charge.dispute.funds_reinstated", dispute))
    assert days_left(shop) == 30


@pytest.mark.spec("API-BILL-021")
def test_checkout_is_refused_when_there_is_nothing_to_sell(
    make_harness: Callable[..., Harness], stripe: FakeStripe
) -> None:
    shop = make_harness(allow_self_upgrade=True)
    shop.container.payments = StripePayments(API_KEY, HOOK_KEY, api=stripe)
    register(shop.client, "ada@example.com")
    for _ in range(2):
        post_event(shop, paid_event(buy(shop, stripe)))
    calls = list(stripe.calls)
    assert shop.client.post(CHECKOUT).status_code == 409
    age_passes(shop, 100)
    shop.client.post("/api/v1/auth/upgrade")
    assert shop.client.post(CHECKOUT).status_code == 409
    assert stripe.calls == calls


@pytest.mark.spec("API-BILL-022")
def test_other_mode_and_unknown_sessions_do_not_block(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    players = store_of(shop)
    asyncio.run(
        players.create_purchase("ada@example.com", amount_cents=500, currency="usd", livemode=True)
    )
    buy(shop, stripe)
    stripe.sessions.clear()
    buy(shop, stripe)
    assert len(stripe.sessions) == 1


@pytest.mark.spec("API-BILL-023")
def test_stripe_outage_never_opens_a_second_session(shop: Harness, stripe: FakeStripe) -> None:
    register(shop.client, "ada@example.com")
    purchase_id = buy(shop, stripe)
    stripe.fail = True
    assert shop.client.post(CHECKOUT).status_code == 503
    assert sync(shop).status_code == 503
    assert sync(shop, cancel=True).status_code == 503
    assert store_of(shop)._purchases[purchase_id].status == "pending"
    assert delete_account(shop.client).status_code == 204
