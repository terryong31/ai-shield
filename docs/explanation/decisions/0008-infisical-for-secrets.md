# 0008. Infisical for secrets

- **Status:** Proposed
- **Date:** 2026-11-25

## Context

The gateway and the web client need secrets for several providers (Supabase, Redis, Google, Groq,
TypeSafe, Stripe) in two environments. Local `.env` files are different on each computer, are easy to
commit by mistake, and do not show who changed a value.

## Decision

- Infisical holds the secrets, in the environments `dev` and `prod`, with the paths `/api` and `/web`.
- The mise tasks start processes with `infisical run`. mise pins the CLI.
- `.infisical.json` is committed. It has the project id and no secret.
- Local Supabase credentials do not go into Infisical. `scripts/local_env.py` reads them from the
  local stack.
- `apps/api/.env` stays as an optional local override.
- Tests and CI do not use Infisical.

## Consequences

- One place to change a secret, with access control for each environment.
- `mise run dev` needs an Infisical account and the network. A person without access starts the
  processes directly ([Manage secrets](../../how-to/manage-secrets.md)).
- `infisical secrets` prints values, so use it with care in a shared terminal.
- Production still reads its variables from Vercel.
