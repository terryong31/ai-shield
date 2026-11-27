# 0054 — Backend security hardening: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Changes span `apps/api`, `packages/engine` (CSV parsing only), `supabase/config.toml`, and `compose.yaml` (no Supabase migrations or `apps/web` changes):

1. **Middleware and error handling (`main.py`):**
   - Sanitize `RequestValidationError` responses in the custom exception handler by stripping `"input"` and raw values from `"ctx"`.
   - Enforce `x-shield-proxy-secret` in production on **every** route except `GET /api/v1/health` and `POST /api/v1/billing/webhook` (and keep `x-shield-botid: pass` on `botid_paths`, including `/clearance`).
   - Replace `await request.body()` buffering with a streaming body-size middleware (256 KiB default, 1.25 MiB for `/game/train`, 256 KiB for `/billing/webhook`) that caches the bounded body or rejects with `413` as soon as the limit is exceeded.
   - Add CSRF `Origin` / `Sec-Fetch-Site` verification for mutating methods (excluding `/billing/webhook`).
   - Add baseline security response headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`, production `Strict-Transport-Security`) and `Cache-Control: private, no-store` on authenticated routes.
2. **Client IP and rate limits (`dependencies.py`, `routers/auth.py`, `routers/clearance.py`):**
   - Require `TRUSTED_PROXY_SECRET` before reading `TRUSTED_CLIENT_IP_HEADER` and read the rightmost IP (`raw.rsplit(",", 1)[-1].strip()`).
   - Add rate limits to `/auth/confirm`, `/auth/reset-password`, per-email `/auth/register`, and per-email `/clearance`; reset `login_fail` on valid login.
3. **Schemas (`schemas.py`):**
   - Introduce a `StrictRequestModel(BaseModel)` with `ConfigDict(extra="forbid")` and inherit all request schemas from it.
   - Add `max_length` bounds to board IDs, positions, training text/rows, and a validator capping `BoardNodeSchema.config` keys (32), nesting depth (4), and serialized size (16 KiB).
4. **Auth flows, sessions, and spend (`routers/auth.py`, `routers/account.py`, `routers/clearance.py`, `routers/game.py`, `services/players.py`, `services/spend.py`):**
   - Check `flow.purpose` in `/auth/confirm` and `/auth/reset-password`, and return `400` in `/auth/confirm` when no verification path runs.
   - Set `samesite="strict"` on `shield_session`.
   - Rotate `shield_player_session` on `/auth/account/password` and `/auth/upgrade`.
   - Add per-owner concurrency serialization around quota-counted runs in `POST /game/run` (local `asyncio.Lock` per owner, or Redis lock when Redis is configured) so concurrent requests cannot race `SpendLedger.ensure_within()`.
5. **Subprocess isolation, audit logging, and startup guards (`services/train_worker.py`, `container.py`, `Dockerfile`):**
   - Build a minimal allowlisted `env` dict for `asyncio.create_subprocess_exec` in `TrainWorkerRunner`.
   - Enforce minimum 32-byte `MODEL_SIGNING_KEY` and strict production checks (`https://` `WEB_BASE_URL`, `SESSION_COOKIE_SECURE=True`, `ALLOW_SELF_UPGRADE=False`, `rediss://` `REDIS_URL`) in `container.py`.
   - Emit structured security audit logs for admin and account lifecycle events.
   - Add `--no-server-header` to `apps/api/Dockerfile`.
6. **Engine CSV bounds (`packages/engine/src/shield_engine/game/__init__.py`, `custom.py`) & infra config (`supabase/config.toml`, `compose.yaml`):**
   - Use `itertools.islice(reader, max_rows + 2)` in `parse_dataset_csv()` and `parse_custom_dataset()` and strip `Cf`/`Cs` characters in `_clean_training_text()`.
   - Update `supabase/config.toml` (`auto_expose_new_tables = false`, `minimum_password_length = 8`, `password_requirements = "lower_upper_letters_digits"`) and bind Redis to `127.0.0.1:6379:6379` in `compose.yaml`.
7. **Operational dashboard / CLI checklist (manual or ops runbook):**
   - Supabase Dashboard: enable Leaked Password Protection and DB SSL enforcement.
   - Vercel `ai-shield`: switch Bot Protection from `Log` to `Challenge`.
   - Vercel `ai-shield-backend`: add a Firewall rule blocking direct traffic missing `x-shield-proxy-secret` (except `/api/v1/health` and `/api/v1/billing/webhook`), and delete unused `STRIPE_API_KEY` from Production env.

## Interfaces

No new HTTP routes. Existing response models remain backward-compatible. Request schemas become stricter (`additionalProperties: false` and explicit `maxLength`/`maxItems`); run `mise run contract` to update `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New configuration constraints are documented in `docs/reference/configuration.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Double-submit CSRF token cookie | Adds frontend state and header wiring; `Origin` + `Sec-Fetch-Site` + `SameSite` achieves equivalent protection for same-origin JSON APIs without client changes. |
| Migrate trained models from `pickle` to `skops.io` | Adds a new dependency and touches `packages/engine`; out of scope for this `apps/api` hardening pass. |
| Bind `clearance_sessions` to `admin_user_id` | Requires a Supabase migration and `SessionStore` protocol changes; track in a dedicated follow-up spec. |

## Risks and rollback

- **Strict `Origin`/`Sec-Fetch-Site` check:** Could block non-browser scripts calling production endpoints with session cookies; verified safe because browsers send `Origin` and/or `Sec-Fetch-Site` on mutating requests, and `/billing/webhook` is exempt.
- **Rightmost IP parsing:** Verify `TRUSTED_CLIENT_IP_HEADER` in production (e.g., `X-Vercel-Forwarded-For` or `X-Forwarded-For`) appends the real client IP on the right; revertible by configuration or single-line rollback in `dependencies.py`.
- **`rediss://` in production:** Ensure production `REDIS_URL` in Infisical uses `rediss://` before deploying.
