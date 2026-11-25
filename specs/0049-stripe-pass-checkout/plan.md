# 0049 — Stripe pass checkout (sandbox): implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Add `routers/billing.py`, `services/billing.py` (a `PaymentGateway` Protocol with a Stripe adapter and a fake), and one migration (`players.accounts.paid_until`, `players.purchases`, and an atomic RPC that fulfils a purchase once). Compute the effective tier in the player stores. Update `plans.vue`. Run `mise run contract`.

## Boundaries check

- [ ] The engine does not change
- [ ] The web client uses only the contract
- [ ] New configuration is in `docs/reference/configuration.md`

## Risks and rollback

Revert the release; new columns and tables are additive.
