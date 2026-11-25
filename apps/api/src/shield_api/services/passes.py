"""Settles pass purchases: every known payment is granted or refunded (spec 0049)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

from shield_api.schemas import PlayerSessionStatus
from shield_api.services.billing import (
    PASS_CURRENCY,
    PASS_DAYS,
    PASS_PRICE_CENTS,
    CheckoutState,
    PaymentEvent,
    PaymentProvider,
    PaymentUnavailableError,
)
from shield_api.services.players import PlayerStore, PurchaseOutcome, PurchasePendingError

logger = logging.getLogger(__name__)

SyncState = Literal["none", "open", "processing", "paid"]
# A purchase without a session is being created by another request for this long.
CREATING_SECONDS = 60
# Do not send a player to a page that is about to expire.
REUSE_MARGIN_SECONDS = 120
MAX_REMAINING = timedelta(days=PASS_DAYS)


class CheckoutRefusedError(Exception):
    """There is nothing to sell right now; the message is for the player."""


class RetryEventError(Exception):
    """Stripe must deliver the event again."""


class PassDesk:
    def __init__(self, players: PlayerStore, payments: PaymentProvider) -> None:
        self._players = players
        self._payments = payments

    async def start(self, player: PlayerSessionStatus, plans_url: str) -> str:
        """Return the Stripe page for the one open checkout of this player."""
        email = player.email
        assert email is not None
        now = datetime.now(UTC)
        if player.paid_until is not None and player.paid_until > now + MAX_REMAINING:
            raise CheckoutRefusedError("You can extend when 30 days or less remain.")
        if player.tier == "paid" and (player.paid_until is None or player.paid_until <= now):
            raise CheckoutRefusedError("Your account already has the Paid plan.")

        if url := await self._reuse(email):
            return url
        try:
            purchase_id = await self._players.create_purchase(
                email,
                amount_cents=PASS_PRICE_CENTS,
                currency=PASS_CURRENCY,
                livemode=self._payments.livemode,
            )
        except PurchasePendingError:
            raise CheckoutRefusedError(
                "A checkout is already starting. Try again in a moment."
            ) from None
        try:
            session_id, url = await self._payments.checkout(
                purchase_id=purchase_id,
                email=email,
                success_url=f"{plans_url}?checkout=success",
                cancel_url=f"{plans_url}?checkout=cancelled",
            )
            await self._players.attach_session(purchase_id, session_id)
        except Exception:
            await self._players.expire_purchase(purchase_id)
            raise
        return url

    async def _reuse(self, email: str) -> str | None:
        pending = await self._players.pending_purchase(email, livemode=self._payments.livemode)
        if pending is None:
            return None
        if pending.session_id is None:
            if datetime.now(UTC) - pending.created_at < timedelta(seconds=CREATING_SECONDS):
                raise CheckoutRefusedError("A checkout is already starting. Try again in a moment.")
            await self._players.expire_purchase(pending.id)
            return None
        state = await self._payments.state(pending.session_id)
        if state.state == "open":
            if state.url and state.expires_at > time.time() + REUSE_MARGIN_SECONDS:
                return state.url
            state = await self._payments.close(pending.session_id)
        result = await self._apply(pending.id, state)
        if result == "paid":
            raise CheckoutRefusedError("Your earlier payment went through. Your pass is active.")
        if result != "none":
            raise CheckoutRefusedError("Your earlier payment is still processing.")
        return None

    async def sync(self, email: str, *, cancel: bool) -> SyncState:
        """Ask Stripe about the open checkout, for a missed webhook or a cancelled page."""
        pending = await self._players.pending_purchase(email, livemode=self._payments.livemode)
        if pending is None or pending.session_id is None:
            return "none"
        ask = self._payments.close if cancel else self._payments.state
        return await self._apply(pending.id, await ask(pending.session_id))

    async def close_open_checkout(self, email: str) -> None:
        """Best effort before an account deletion; a late payment is refunded anyway."""
        try:
            pending = await self._players.pending_purchase(email, livemode=self._payments.livemode)
            if pending is not None and pending.session_id is not None:
                await self._payments.close(pending.session_id)
        except Exception as err:
            logger.warning("could not close an open checkout (%s)", type(err).__name__)

    async def _apply(self, purchase_id: str, state: CheckoutState) -> SyncState:
        if state.state == "paid":
            await self._grant(
                PaymentEvent(
                    "paid", purchase_id, state.payment_intent, state.amount_cents, state.currency
                )
            )
            return "paid"
        if state.state == "expired":
            await self._players.expire_purchase(purchase_id)
            return "none"
        return state.state

    async def handle(self, event: PaymentEvent) -> None:
        """Apply a signed event. Raises ``RetryEventError`` when Stripe must retry."""
        if event.kind == "paid":
            await self._grant(event)
        elif event.kind == "ended" and event.purchase_id:
            await self._players.expire_purchase(event.purchase_id)
        elif event.kind in {"refunded", "disputed"}:
            outcome = await self._players.revoke_purchase(
                purchase_id=event.purchase_id,
                payment_intent=event.payment_intent,
                status="refunded" if event.kind == "refunded" else "disputed",
            )
            self._report(event, outcome)
        elif event.kind in {"refund_failed", "dispute_won"} and event.payment_intent:
            outcome = await self._players.restore_purchase(
                event.payment_intent,
                status="refunded" if event.kind == "refund_failed" else "disputed",
            )
            self._report(event, outcome)

    async def _grant(self, event: PaymentEvent) -> None:
        assert event.purchase_id is not None
        outcome = await self._players.fulfil_purchase(
            event.purchase_id,
            payment_intent=event.payment_intent,
            amount_cents=event.amount_cents,
            currency=event.currency,
            days=PASS_DAYS,
        )
        if outcome == "orphaned" and event.payment_intent:
            # The account was deleted while the player paid: give the money back.
            try:
                await self._payments.refund(event.purchase_id, event.payment_intent)
            except PaymentUnavailableError:
                raise RetryEventError from None
            await self._players.revoke_purchase(
                purchase_id=event.purchase_id,
                payment_intent=event.payment_intent,
                status="refunded",
            )
            logger.warning("refunded purchase %s of a deleted account", event.purchase_id)
            return
        self._report(event, outcome)

    def _report(self, event: PaymentEvent, outcome: PurchaseOutcome) -> None:
        name = event.purchase_id or event.payment_intent
        if outcome == "no_account":
            # An email change is moving the account.
            raise RetryEventError
        if outcome in {"mismatch", "orphaned"}:
            logger.error("Stripe %s for purchase %s needs a person: %s", event.kind, name, outcome)
        elif outcome == "unknown":
            logger.warning("Stripe %s for an unknown purchase %s", event.kind, name)
