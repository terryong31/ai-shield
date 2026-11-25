"""Stripe Checkout for the 30-day pass (spec 0049).

Card data never reaches the gateway. Stripe is the source of truth for payments:
the gateway grants a pass only from a signed event or from a session read with the key.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

PASS_PRICE_CENTS = 500
PASS_CURRENCY = "usd"  # noqa: S105 (a currency)
PASS_DAYS = 30
WEBHOOK_TOLERANCE_SECONDS = 300
# Stripe refuses less than 30 minutes; the margin covers clock differences.
SESSION_SECONDS = 1860
STRIPE_TIMEOUT_SECONDS = 10
TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")
LIVE_KEY_PREFIXES = ("sk_live_", "rk_live_")
PAID_EVENTS = frozenset({"checkout.session.completed", "checkout.session.async_payment_succeeded"})
ENDED_EVENTS = frozenset({"checkout.session.expired", "checkout.session.async_payment_failed"})

EventKind = Literal[
    "paid", "ended", "refunded", "refund_failed", "disputed", "dispute_won", "ignored"
]


class InvalidWebhookError(Exception):
    """The signature is wrong or old, or the signed body is not an event."""


class PaymentUnavailableError(Exception):
    """Stripe did not answer, or refused the request."""


@dataclass(frozen=True)
class PaymentEvent:
    kind: EventKind
    purchase_id: str | None = None
    payment_intent: str | None = None
    amount_cents: int = 0
    currency: str = ""


@dataclass(frozen=True)
class CheckoutState:
    """What Stripe says about one session."""

    state: Literal["open", "processing", "paid", "expired"]
    url: str | None = None
    expires_at: int = 0
    payment_intent: str | None = None
    amount_cents: int = 0
    currency: str = ""


class StripeApi(Protocol):
    """The Stripe calls the gateway needs, with plain dictionaries."""

    def create(self, params: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...

    def retrieve(self, session_id: str) -> dict[str, Any] | None:
        """``None`` when Stripe does not know the session."""
        ...

    def expire(self, session_id: str) -> bool:
        """``False`` when the session is not open any more."""
        ...

    def refund(self, payment_intent: str, idempotency_key: str) -> None:
        """Does nothing when the payment is already refunded or disputed."""
        ...


class PaymentProvider(Protocol):
    @property
    def livemode(self) -> bool: ...

    async def checkout(
        self, *, purchase_id: str, email: str, success_url: str, cancel_url: str
    ) -> tuple[str, str]:
        """Return the session id and its page. Raises ``PaymentUnavailableError``."""
        ...

    async def state(self, session_id: str) -> CheckoutState: ...

    async def close(self, session_id: str) -> CheckoutState:
        """Expire an open session and return what it became."""
        ...

    async def refund(self, purchase_id: str, payment_intent: str) -> None: ...

    def read_event(self, payload: bytes, signature: str) -> PaymentEvent:
        """Verify and parse a webhook. Raises ``InvalidWebhookError``."""
        ...


class _StripeSdk:
    def __init__(self, secret_key: str) -> None:
        import stripe

        self._stripe = stripe
        self._client = stripe.StripeClient(
            secret_key,
            max_network_retries=2,
            http_client=stripe.RequestsClient(timeout=STRIPE_TIMEOUT_SECONDS),
        )

    def create(self, params: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        session = self._client.v1.checkout.sessions.create(
            params,  # type: ignore[arg-type]
            {"idempotency_key": idempotency_key},
        )
        return dict(session.to_dict())

    def retrieve(self, session_id: str) -> dict[str, Any] | None:
        try:
            return dict(self._client.v1.checkout.sessions.retrieve(session_id).to_dict())
        except self._stripe.InvalidRequestError as err:
            if err.code == "resource_missing":
                return None
            raise

    def expire(self, session_id: str) -> bool:
        try:
            self._client.v1.checkout.sessions.expire(session_id)
        except self._stripe.InvalidRequestError:
            return False
        return True

    def refund(self, payment_intent: str, idempotency_key: str) -> None:
        try:
            self._client.v1.refunds.create(
                {"payment_intent": payment_intent}, {"idempotency_key": idempotency_key}
            )
        except self._stripe.InvalidRequestError as err:
            if err.code not in {"charge_already_refunded", "charge_disputed"}:
                raise


def _purchase_id(value: Any) -> str | None:
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _checkout_state(session: dict[str, Any] | None) -> CheckoutState:
    if session is None:
        return CheckoutState("expired")
    status = session.get("status")
    state: Literal["open", "processing", "paid", "expired"] = "expired"
    if session.get("payment_status") == "paid":
        state = "paid"
    elif status == "open":
        state = "open"
    elif status == "complete":
        state = "processing"
    return CheckoutState(
        state,
        url=_text(session.get("url")),
        expires_at=int(session.get("expires_at") or 0),
        payment_intent=_text(session.get("payment_intent")),
        amount_cents=int(session.get("amount_total") or 0),
        currency=str(session.get("currency") or ""),
    )


class StripePayments:
    def __init__(
        self, secret_key: str, webhook_secret: str, *, api: StripeApi | None = None
    ) -> None:
        self._webhook_secret = webhook_secret
        self._livemode = secret_key.startswith(LIVE_KEY_PREFIXES)
        self._api: StripeApi = api or _StripeSdk(secret_key)

    @property
    def livemode(self) -> bool:
        return self._livemode

    async def _run[T](self, call: Callable[[], T]) -> T:
        try:
            return await asyncio.to_thread(call)
        except Exception as err:
            # Stripe messages can echo request data, so keep only the type.
            raise PaymentUnavailableError(type(err).__name__) from None

    async def checkout(
        self, *, purchase_id: str, email: str, success_url: str, cancel_url: str
    ) -> tuple[str, str]:
        params: dict[str, Any] = {
            "mode": "payment",
            "client_reference_id": purchase_id,
            "customer_email": email,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "expires_at": int(time.time()) + SESSION_SECONDS,
            # Cards settle immediately and always in the price currency.
            "allowed_payment_method_types": ["card"],
            "adaptive_pricing": {"enabled": False},
            # Charges copy this metadata, so a refund event names its purchase.
            "payment_intent_data": {"metadata": {"purchase_id": purchase_id}},
            "line_items": [
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": PASS_CURRENCY,
                        "unit_amount": PASS_PRICE_CENTS,
                        "product_data": {"name": f"ai-shield Paid, {PASS_DAYS}-day pass"},
                    },
                }
            ],
        }
        session = await self._run(lambda: self._api.create(params, purchase_id))
        session_id, url = _text(session.get("id")), _text(session.get("url"))
        if not session_id or not url:
            raise PaymentUnavailableError("incomplete session")
        return session_id, url

    async def state(self, session_id: str) -> CheckoutState:
        return _checkout_state(await self._run(lambda: self._api.retrieve(session_id)))

    async def close(self, session_id: str) -> CheckoutState:
        if await self._run(lambda: self._api.expire(session_id)):
            return CheckoutState("expired")
        return await self.state(session_id)

    async def refund(self, purchase_id: str, payment_intent: str) -> None:
        await self._run(lambda: self._api.refund(payment_intent, f"refund-{purchase_id}"))

    def read_event(self, payload: bytes, signature: str) -> PaymentEvent:
        import stripe

        try:
            text = payload.decode("utf-8")
            stripe.WebhookSignature.verify_header(
                text, signature, self._webhook_secret, WEBHOOK_TOLERANCE_SECONDS
            )
            event = json.loads(text)
            kind, livemode, obj = event["type"], event["livemode"], event["data"]["object"]
        except (stripe.SignatureVerificationError, ValueError, KeyError, TypeError):
            raise InvalidWebhookError from None
        if not isinstance(obj, dict):
            raise InvalidWebhookError
        if livemode is not self._livemode:
            return PaymentEvent("ignored")
        return _read_object(str(kind), obj)


def _read_object(kind: str, obj: dict[str, Any]) -> PaymentEvent:
    intent = _text(obj.get("payment_intent"))
    if kind in PAID_EVENTS | ENDED_EVENTS:
        purchase_id = _purchase_id(obj.get("client_reference_id"))
        if purchase_id is None or obj.get("mode") != "payment":
            return PaymentEvent("ignored")
        if kind in ENDED_EVENTS:
            return PaymentEvent("ended", purchase_id)
        state = _checkout_state(obj)
        if state.state != "paid":
            return PaymentEvent("ignored")
        return PaymentEvent("paid", purchase_id, intent, state.amount_cents, state.currency)
    if kind == "charge.refunded" and obj.get("refunded") is True:
        metadata = obj.get("metadata")
        purchase_id = _purchase_id(
            metadata.get("purchase_id") if isinstance(metadata, dict) else None
        )
        if purchase_id or intent:
            return PaymentEvent("refunded", purchase_id, intent)
    elif intent and (
        kind == "refund.failed"
        or (kind == "refund.updated" and obj.get("status") in {"failed", "canceled"})
    ):
        return PaymentEvent("refund_failed", None, intent)
    # Inquiries move no money, so only the funds events change a pass.
    elif intent and kind == "charge.dispute.funds_withdrawn":
        return PaymentEvent("disputed", None, intent)
    elif intent and kind == "charge.dispute.funds_reinstated":
        return PaymentEvent("dispute_won", None, intent)
    return PaymentEvent("ignored")
