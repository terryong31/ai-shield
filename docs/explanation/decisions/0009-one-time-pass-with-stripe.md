# 0009. One-time pass with Stripe Checkout

- **Status:** Accepted
- **Date:** 2026-11-25

## Context

The Paid tier needed a way to pay. This is a small project that must be easy to close.

Alternatives considered:

- **Monthly subscription.** To close the app, the owner must cancel each customer. It also needs
  code for renewals and failed payments.
- **Credits.** Unused balances are a debt when the app closes. Credits also replace the daily quotas.
- **Embedded payment form.** It adds a web dependency and puts payment code on the site.

## Decision

- Sell a 30-day pass for USD 5: one payment, no renewal.
- Use Stripe-hosted Checkout, with cards only and in USD only.
- Stripe is the source of truth. The gateway grants a pass only from a signed webhook, or from a
  session that it reads with the secret key. The browser never grants a pass.
- Each known payment ends in a granted pass or a refund. Other cases are logged for a person.
- A pass ends 60 days from now at the most.
- Development and production use a sandbox until the owner changes the keys.

## Consequences

- To close the app, stop sales and wait 60 days.
- Card data never reaches the app.
- Players must buy again. There is no automatic renewal.
- While production uses the sandbox, a public test card gives the Paid tier and its model costs.
- Each Stripe API change can break checkout. Test with a real sandbox session after an SDK update.
