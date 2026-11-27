# AGENTS.md: apps/api

The game gateway. Root rules in [../../AGENTS.md](../../AGENTS.md) apply; these add to them.

## Map

| Path | Responsibility |
| --- | --- |
| `routers/` | HTTP mapping only: parse, call a service/engine, shape the response |
| `routers/game.py` | Levels, runs (quota, custom sandbox), saves, scores, ML training |
| `routers/auth.py` | Player sessions: anonymous, register, login, recover, upgrade, logout |
| `routers/account.py` | Account settings: display name, password, email, reset, delete |
| `routers/billing.py` | Pass checkout, sync and the Stripe webhook (spec 0049) |
| `routers/clearance.py` | `POST/GET/DELETE /clearance`: the only route that sees an admin's password |
| `services/admins.py` | Admin check: Supabase Auth sign-in plus `app_metadata.role == "admin"` |
| `admin_cli.py` | `mise run admin:create` / `admin:revoke`: grant or remove the admin role (`admin:remote:*` for the hosted project) |
| `services/clearance.py` | admin session cookie → `Clearance` (fail closed) |
| `services/sessions.py` | Admin clearance sessions (hashed tokens) and the failed-attempt limiter |
| `services/players.py` | Player accounts, sessions, daily quotas and saved boards |
| `services/billing.py` | `PaymentProvider` and `StripeApi` ports, and the Stripe adapter |
| `services/passes.py` | `PassDesk`: every known payment is granted or refunded |
| `services/auth_flows.py` | Email links bound to the browser (spec 0047) |
| `services/leaderboard.py`, `rate_limit.py` | Redis leaderboard and rate limits |
| `services/anonymous_scores.py` | Anonymous players' scores, keyed by the session token hash, until sign-in moves them (spec 0052) |
| `services/scores.py` | `ScoreStore` protocol (leaderboard): Supabase (production/local), in-memory test double |
| `providers/` | Model adapters: Gemini (standard-tier agent) and the BYOK provider allowlist |
| `container.py` | Composition root; the only place that reads provider settings |
| `schemas.py` | Public contract (HTTP models) |

## Rules

- No detection logic here. If you are about to compare a score to a threshold,
  it belongs in `packages/engine`.
- Routers depend on `ContainerDep`; tests build a `Container` with fakes and
  call `create_app(container)`. Never patch module globals.
- Changing `schemas.py` changes the contract: run `mise run contract`, commit
  `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.
- Stream errors are generic (`GENERIC_ERROR`); log details server-side with `logger.exception`.
- Never log or persist an admin's password or a raw session token. Store only the token's
  SHA-256 hash; audit metadata keeps only `clearance` (API-CLEAR-016).
- Admin is `app_metadata.role`, never `user_metadata` (users can write it).
- Demo tool risk labels are part of the security boundary (API-TOOLS-001).

## Security anti-patterns (do not repeat)

Follow these rules on every new route, schema, service, or middleware in `apps/api`:

- **Never echo sensitive fields in 422 responses.** Do not rely on FastAPI's default
  `RequestValidationError` handler to serialize raw `"input"` values, and wrap
  passwords, API keys, and tokens in `SecretStr` or strip `"input"` globally.
- **Never trust the leftmost IP or an unauthenticated proxy header.** When reading
  `TRUSTED_CLIENT_IP_HEADER`, require a verified `TRUSTED_PROXY_SECRET` first (fail
  closed to socket `peer`) and take the rightmost proxy-appended IP, never `split(",")[0]`.
- **Never leave auth, recovery, confirmation, or admin routes unthrottled.** Every
  credential, token-verification, email-sending, or admin endpoint must have rate
  limits (IP plus account/email where applicable), reset failure counters on valid
  sign-in, and sit behind BotID in production.
- **Never buffer unbounded request bodies or parse unbounded JSON.** Enforce
  streaming byte limits before JSON/Pydantic parsing (like `stripe_webhook` does),
  and bound every `list`, `dict`, `str`, and nested `dict[str, Any]` field in `schemas.py`.
- **Never omit `extra="forbid"` on request models.** Every Pydantic request model
  must reject unknown fields (`ConfigDict(extra="forbid")`).
- **Never rely on `SameSite=Lax` alone for state-changing routes.** Verify `Origin`
  and `Sec-Fetch-Site` on mutating endpoints (except signed webhooks), use
  `SameSite=Strict` for admin cookies, and set `Cache-Control: private, no-store`
  plus baseline security headers on responses.
- **Never skip `flow.purpose` or fall through silently in auth confirmation.** Verify
  the flow purpose matches the endpoint and fail closed (`400`) if no verification
  branch ran.
- **Never spawn subprocesses with inherited `os.environ`.** Pass an explicit
  allowlisted `env` so `SUPABASE_KEY`, `STRIPE_SECRET_KEY`, LLM keys, and
  `REDIS_URL` are not exposed to worker processes.
- **Never keep the same session token across password change or privilege elevation.**
  Rotate the session cookie and revoke the old token.
- **Never check-then-update spend or quotas without serialization or atomic ops.**
  Avoid TOCTOU races between checking a budget and recording usage after an async call.
- **Never allow insecure production defaults.** In `APP_ENV="production"`, require
  `https://` for `WEB_BASE_URL`, `rediss://` for `REDIS_URL`, `SESSION_COOKIE_SECURE=True`,
  `ALLOW_SELF_UPGRADE=False`, and high-entropy signing keys (at least 32 bytes).
- **Never expose gateway routes directly without the proxy secret in production.**
  Every production route except `GET /api/v1/health` and `POST /api/v1/billing/webhook`
  must verify `x-shield-proxy-secret` so callers cannot bypass the web proxy or WAF.
- **Never materialize unbounded CSVs or bind local backing services to `0.0.0.0`.**
  Bound CSV iteration before allocating rows, strip `Cf`/`Cs` Unicode control
  characters, and bind local Redis in `compose.yaml` to `127.0.0.1` only.

## Commands

```bash
mise run api:dev            # http://localhost:8000/api/v1/docs
mise run test:api
```
