"""Pass checkout and the Stripe webhook (spec 0049)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from shield_api.container import Container
from shield_api.dependencies import PLAYER_SESSION_COOKIE, ContainerDep, enforce_rate_limit
from shield_api.schemas import (
    BillingCheckoutResponse,
    BillingSyncRequest,
    BillingSyncResponse,
    PlayerSessionStatus,
)
from shield_api.services.billing import InvalidWebhookError
from shield_api.services.passes import CheckoutRefusedError, PassDesk
from shield_api.services.rate_limit import (
    BILLING_SYNC_LIMIT,
    BILLING_SYNC_WINDOW,
    CHECKOUT_LIMIT,
    CHECKOUT_WINDOW,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])

SIGN_IN_REQUIRED = "Sign in to buy a pass."
UNAVAILABLE = "Payments are unavailable. Try again later."
MAX_WEBHOOK_BYTES = 262_144

_PLAYER_ERRORS: dict[int | str, dict[str, str]] = {
    403: {"description": "Sign in to buy a pass."},
    429: {"description": "Too many requests."},
    503: {"description": "Payments are unavailable."},
}


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)


def _desk(container: Container) -> PassDesk:
    if container.payments is None:
        raise _unavailable()
    return PassDesk(container.players, container.payments)


async def _buyer(
    request: Request, container: Container, *, bucket: str, limit: int, window: int
) -> tuple[PlayerSessionStatus, str]:
    player = await container.players.lookup(request.cookies.get(PLAYER_SESSION_COOKIE))
    if not player.authenticated or player.is_anonymous or not player.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SIGN_IN_REQUIRED)
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter, bucket, player.email, limit=limit, window_seconds=window
        )
    return player, player.email


@router.post(
    "/checkout",
    responses={**_PLAYER_ERRORS, 409: {"description": "There is nothing to buy right now."}},
)
async def start_checkout(request: Request, container: ContainerDep) -> BillingCheckoutResponse:
    """Return the Stripe page for one 30-day pass; one open page for each player."""
    player, _ = await _buyer(
        request, container, bucket="checkout", limit=CHECKOUT_LIMIT, window=CHECKOUT_WINDOW
    )
    desk = _desk(container)
    plans_url = f"{container.settings.WEB_BASE_URL.strip().rstrip('/')}/plans"
    try:
        return BillingCheckoutResponse(url=await desk.start(player, plans_url))
    except CheckoutRefusedError as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from None
    except Exception as err:
        logger.error("checkout failed (%s)", type(err).__name__)
        raise _unavailable() from None


@router.post("/sync", responses=_PLAYER_ERRORS)
async def sync_checkout(
    body: BillingSyncRequest, request: Request, container: ContainerDep
) -> BillingSyncResponse:
    """Settle the open checkout with Stripe; ``cancel`` expires it when it is not paid."""
    _, email = await _buyer(
        request,
        container,
        bucket="billing_sync",
        limit=BILLING_SYNC_LIMIT,
        window=BILLING_SYNC_WINDOW,
    )
    desk = _desk(container)
    try:
        state = await desk.sync(email, cancel=body.cancel)
        session = await container.players.lookup(request.cookies.get(PLAYER_SESSION_COOKIE))
    except Exception as err:
        logger.error("checkout sync failed (%s)", type(err).__name__)
        raise _unavailable() from None
    return BillingSyncResponse(state=state, session=session)


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "The signature or the event is not valid."},
        503: {"description": "The event could not be applied; Stripe retries."},
    },
)
async def stripe_webhook(request: Request, container: ContainerDep) -> Response:
    """Apply a signed Stripe event."""
    desk = _desk(container)
    assert container.payments is not None
    payload = b""
    async for chunk in request.stream():
        payload += chunk
        if len(payload) > MAX_WEBHOOK_BYTES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook.")
    try:
        event = container.payments.read_event(payload, request.headers.get("stripe-signature", ""))
    except InvalidWebhookError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook.") from None
    try:
        await desk.handle(event)
    except Exception as err:
        logger.error("could not apply a Stripe %s event (%s)", event.kind, type(err).__name__)
        raise _unavailable() from None
    return Response(status_code=status.HTTP_200_OK)
