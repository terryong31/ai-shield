# 0049 — Stripe pass checkout (sandbox)

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-25
- **Related:** [0020](../0020-game-ai-agent/spec.md) (tiers and quotas), [0025](../0025-account-settings/spec.md), [0041](../0041-same-origin-api-proxy/spec.md)

## Problem

`/plans` shows a Paid plan at $0 and the button is disabled in production. No payment exists.

## Goals

- A player can buy a **30-day pass** for **USD 5** with Stripe-hosted Checkout. It is one payment and does not renew.
- Development and production both use a Stripe sandbox now. The owner goes live by a change of keys, with no code change.
- The app is easy to close: stop sales, and the last pass ends after 30 days.

## Non-goals

- Subscriptions, credits, coupons, tax, and a customer portal.

## Behaviour

| Model | Why not |
| --- | --- |
| Subscription | Renewals, failed payments and cancellation; closing the app means cancelling each customer |
| Credits | Unused balances are a debt when the app closes; also needs metering that replaces the daily quotas |

- `POST /api/v1/billing/checkout` (signed-in player) creates a Checkout Session (`mode=payment`, price set by the server, return URLs from `WEB_BASE_URL`) and stores a pending purchase. It returns `{ "url" }`.
- `POST /api/v1/billing/webhook` verifies the Stripe signature on the raw body. Only this route grants a pass. The return page only refreshes the session.
- `checkout.session.completed` or `checkout.session.async_payment_succeeded` with `payment_status=paid` sets `paid_until = max(now, paid_until) + 30 days`. A repeated event has no effect.
- `charge.refunded` (full refund) removes the unused days of that purchase.
- The effective tier is `paid` if the stored tier is `paid` (manual grant) or `paid_until` is in the future; otherwise `free`.
- A player with an active pass can buy again when 30 days or less remain, so a pass never ends more than 60 days from now.

### Money rule

A paid session for a known purchase always ends in one of two results: the pass is granted, or the payment is refunded. A case that cannot be settled automatically is logged at error level with the purchase id only.

| Case | Result |
| --- | --- |
| Player clicks back on Stripe | `/plans?checkout=cancelled` asks the gateway to expire the session |
| Player closes the tab | The session expires 30 minutes after its creation |
| Two clicks, two tabs | One open session for each player; a second click returns the same Stripe page |
| Paid, then connection lost | The webhook grants the pass without the browser |
| Paid, and the webhook did not arrive | The next visit to `/plans` or the next checkout reads the session from Stripe and grants the pass |
| Cancel and pay at the same time | Stripe refuses to expire a paid session; the gateway grants the pass |
| Account deleted with an open session | The session is expired; if it was paid, the payment is refunded |
| Price changed while a session was open | The stored price of the purchase is the reference |
| Refund failed or cancelled | The removed days come back |
| Chargeback | `charge.dispute.funds_withdrawn` removes the unused days; `charge.dispute.funds_reinstated` gives them back. Inquiries change nothing |
| Partial refund | Nothing changes |
| Browser back button after the redirect | The button is usable again |
| Player signed out during payment | The purchase belongs to the account, not to the browser session |
| Sandbox to live change | Purchases of the other mode never block a checkout |

Only cards (and card wallets) are accepted, and adaptive pricing is off, so payments settle immediately in USD.

| Variable (Infisical `/api`, dev and prod) | Purpose |
| --- | --- |
| `STRIPE_SECRET_KEY` | `sk_test_…` or `rk_test_…` now; `sk_live_…` or `rk_live_…` later. Unset: billing is off |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…`; necessary when the key is set |

## Acceptance criteria

- **API-BILL-001**: Given a signed-in player, when they start checkout, then Stripe gets `mode=payment`, USD 500 cents and server-built return URLs, a pending purchase is stored, and the response has the Stripe URL.
- **API-BILL-002**: Given an anonymous player, then the response is `403`; billing off or Stripe unavailable gives `503`; Stripe is not called for a refused player.
- **API-BILL-003**: Given a webhook with a missing, wrong or old signature, then the response is `400` and nothing changes.
- **API-BILL-004**: Given a valid paid event for a known purchase, then `paid_until` moves 30 days; the same or concurrent event again changes nothing.
- **API-BILL-005**: Given an unpaid or unknown session, a session with an amount or currency that differs from the stored purchase, or an event whose `livemode` does not match the configured key, then no pass is granted.
- **API-BILL-006**: Given an expired `paid_until`, then tier, quotas and level access are `free` without a new sign-in.
- **API-BILL-007**: Given a full refund event, then the unused days of that purchase are removed once.
- **API-BILL-008**: Given an unknown key prefix, or a key without a webhook secret, then startup fails with the variable name and never the value.
- **API-BILL-009**: Given an email change or account deletion, then purchases and `paid_until` move with the account, or pending purchases lose the email; a late payment for a deleted account is refunded (API-BILL-016).
- **API-BILL-010**: Given a store error in the webhook, then the response is `503`, so Stripe retries.
- **WEB-BILL-001**: Given `/plans` and a signed-in player with billing on, then Paid shows `$5 / 30 days` with `One payment, does not renew` in its feature list, Free shows `$0` with no billing cycle, and `Buy 30-day pass` redirects to the Stripe URL; with billing off, `Coming soon`.
- **WEB-BILL-002**: Given a return with `checkout=success`, then the page removes the query, polls the session for at most 20 seconds, and shows success only when the tier is `paid`; `checkout=cancelled` changes nothing.
- **WEB-BILL-003**: Given an active pass, then `/plans` shows the end date and an `Extend` button.
- **WEB-BILL-006**: Given a page load of `/plans`, then the server render has the billing state (at most 800 ms wait). Until the billing state is known, Paid shows `$5 / 30 days` and all its features with a loading button, so the price and the feature list do not change after the page loads. Until the session is confirmed, a Paid player also sees a loading button.
- **API-BILL-011**: Given a new checkout, then the Stripe session expires 30 to 35 minutes after creation, accepts only `card`, and has adaptive pricing off.
- **API-BILL-012**: Given a player with an open session, when they start checkout again, then the response has the same Stripe URL and no second session is created; when another request is creating a session at the same time, then the response is `409`.
- **API-BILL-013**: Given `POST /billing/sync` with `cancel: true` and an open session, then Stripe expires it and the purchase is `expired`; given the session was paid, then the pass is granted once and the state is `paid`.
- **API-BILL-014**: Given a paid session whose webhook did not arrive, when the player calls `POST /billing/sync` or starts a checkout, then the pass is granted once; a later webhook changes nothing. A checkout in this case returns `409` and creates no session.
- **API-BILL-015**: Given `checkout.session.expired` or `checkout.session.async_payment_failed`, then a pending purchase is `expired`; given a paid event after that, then the pass is granted.
- **API-BILL-016**: Given an account deletion with an open session, then Stripe expires the session; given a paid event for a purchase without an account, then the payment is refunded once with an idempotency key, and a refund outage gives `503`.
- **API-BILL-017**: Given a purchase stored at another price, then its paid event is compared with the stored price and is granted; given a paid event that does not match, then an error log has the purchase id and no personal data.
- **API-BILL-018**: Given a refund of an expired pass while a newer pass is active, then the newer pass keeps all its days; given a refund of the current pass with a later pass after it, then only the unused days are removed.
- **API-BILL-019**: Given `refund.failed`, or `refund.updated` with status `failed` or `canceled`, for a refunded purchase, then its removed days come back once.
- **API-BILL-020**: Given `charge.dispute.funds_withdrawn`, then the unused days are removed once; given `charge.dispute.funds_reinstated`, then they come back once; `charge.dispute.created` changes nothing.
- **API-BILL-021**: Given a manual Paid grant, or more than 30 days left, then checkout returns `409` and does not call Stripe.
- **API-BILL-022**: Given a pending purchase of the other mode, or a session that Stripe does not know, then checkout continues with a new session.
- **API-BILL-023**: Given Stripe is unavailable while the gateway checks an open session, then checkout and sync return `503` and no second session is created; account deletion continues.
- **WEB-BILL-004**: Given a return with `checkout=cancelled`, then the page calls sync with `cancel: true`; each visit by a signed-in player with billing on calls sync once.
- **WEB-BILL-005**: Given a page restored from the back-forward cache, then the buy button is not loading; given a return with `checkout=success` and no signed-in session, then the toast asks the player to sign in.
- **WEB-BILL-007**: Given a signed-in player, then the main menu always links to `/plans`: `Upgrade Plan` on Free and `Manage Plan` on Paid.

## Security & privacy considerations

Card data never reaches the app. The client sends no price, email or return URL. The webhook is
outside BotID and fails closed on signature errors. Secrets and event bodies are never logged.
`players.purchases` uses RLS deny-by-default like the other tables.

## Evaluation impact

None.

## Open questions

None. The owner chose the 30-day pass, USD 5, and sandbox in both environments with no allowlist (2026-11-25). Accepted risk: while production uses the sandbox, a public test card gives the Paid tier. New dependency `stripe` (Python) was approved on 2026-11-25.

## Verification

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: API-BILL-001, API-BILL-002, API-BILL-003, API-BILL-004, API-BILL-005, API-BILL-006, API-BILL-007, API-BILL-008, API-BILL-009, API-BILL-010, WEB-BILL-001, WEB-BILL-002, WEB-BILL-003
- Red: 13 failing test(s) before implementation (`apps/api/tests/test_billing.py`, `apps/api/tests/test_billing.py`, `apps/api/tests/test_billing.py`)
- Green: 39 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: WEB-BILL-001
- Red: 1 failing test(s) before implementation (`Stripe pass checkout (spec 0049) [WEB-BILL-001] sells a 30-day pass that redirects to Stripe, or shows Coming soon`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: API-BILL-011, API-BILL-012, API-BILL-013, API-BILL-014, API-BILL-015, API-BILL-016, API-BILL-017, API-BILL-018, API-BILL-019, API-BILL-020, API-BILL-021, API-BILL-022, API-BILL-023, WEB-BILL-004, WEB-BILL-005
- Red: 15 failing test(s) before implementation (`apps/api/tests/test_billing.py`, `apps/api/tests/test_billing.py`, `apps/api/tests/test_billing.py`)
- Green: 30 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: API-BILL-011
- Red: 1 failing test(s) before implementation (`apps/api/tests/test_billing.py::test_session_expires_soon_and_takes_only_cards_in_usd`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-BILL-006
- Red: 1 failing test(s) before implementation (`Stripe pass checkout (spec 0049) [WEB-BILL-006] keeps the price and features stable until the billing state is known`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-26 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-BILL-007
- Red: 1 failing test(s) before implementation (`Stripe pass checkout (spec 0049) [WEB-BILL-007] links every signed-in player to the plans from the main menu`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
