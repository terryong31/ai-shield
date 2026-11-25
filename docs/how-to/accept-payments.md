# Accept payments (Stripe)

Players buy a 30-day Paid pass with Stripe-hosted Checkout
([spec 0049](../../specs/0049-stripe-pass-checkout/spec.md)). It costs USD 5. It is one payment, and
it does not renew. Why it works this way: [ADR 0009](../explanation/decisions/0009-one-time-pass-with-stripe.md).

Development and production use a Stripe sandbox at this time. **In the sandbox, a public test card
gives the Paid tier to any player.**

## Set up the sandbox

You need the [Stripe CLI](https://docs.stripe.com/stripe-cli) and access to
[Infisical](manage-secrets.md).

1. Apply the migrations to the hosted database **before** you deploy the API. Without them, email
   change and account deletion fail too.

   ```bash
   mise run db:remote:plan
   mise run db:remote:push
   ```

2. Store the keys and make the production webhook endpoint. The command asks for the sandbox secret
   key and does not show it:

   ```bash
   mise run stripe:setup https://<web URL>
   ```

3. Deploy. `GET /api/v1/game/levels` must return `"billing_enabled": true`.

When the list of events in `scripts/stripe_setup.py` changes, update the endpoint:

```bash
mise run stripe:events https://<web URL>
```

## Test a payment on your computer

1. Run `mise run dev`, and in a second terminal `mise run stripe:listen`.
2. Sign in, open `/plans`, and select **Buy 30-day pass**.
3. Pay with the test card `4242 4242 4242 4242`, any future date and any security code.

To test a refund, refund the payment in the Stripe dashboard. The pass ends when the event arrives.

## Events

| Event | Result |
| --- | --- |
| `checkout.session.completed`, `checkout.session.async_payment_succeeded` | Adds 30 days, one time for each purchase |
| `checkout.session.expired`, `checkout.session.async_payment_failed` | Closes the purchase. A later payment still counts |
| `charge.refunded` (full) | Removes the unused days of that purchase |
| `refund.failed`, `refund.updated` (`failed` or `canceled`) | Gives the removed days back |
| `charge.dispute.funds_withdrawn` | Removes the unused days |
| `charge.dispute.funds_reinstated` | Gives them back |

A partial refund, an inquiry and an early fraud warning change nothing.

If a webhook does not arrive, the next visit to `/plans` or the next checkout reads the session from
Stripe. A payment for a deleted account is refunded automatically.

## Find a problem

| Symptom | What to do |
| --- | --- |
| `/plans` shows `Coming soon` | `STRIPE_SECRET_KEY` is not set. See [Manage secrets](manage-secrets.md) |
| The API does not start: `STRIPE_WEBHOOK_SECRET` | Set the webhook secret together with the key |
| Webhook returns `400` | The secret does not belong to this endpoint. `stripe listen` and the production endpoint have different secrets |
| Webhook returns `503` | The database or Stripe did not answer. Stripe sends the event again: for three days in live mode, three times in a sandbox |
| Log: `Stripe ... needs a person: mismatch` | The paid amount is not the price of the purchase. Compare the purchase id with Stripe, then refund or grant it |
| Log: `Stripe ... needs a person: orphaned` | A refund failed for a deleted account. Refund the customer in a different way |
| Checkout returns `409` | A payment is processing, or the pass has more than 30 days left |

## Go live

1. Remove sandbox passes from the production database. They stay active after the change of keys.
2. Make a live webhook endpoint in Stripe for `https://<web URL>/api/v1/billing/webhook`, with the
   events in the table above.
3. Replace `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in Infisical `prod /api` with the live
   values, and deploy. No code changes. Sandbox purchases do not block live checkouts.
4. Turn on email receipts in the Stripe dashboard.

`mise run stripe:setup` refuses live keys.

## Stop sales

Remove `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` from `prod /api` and deploy. The last pass
ends 60 days later at the most. Refunds made after this change do not remove days, because the
webhook is off.
