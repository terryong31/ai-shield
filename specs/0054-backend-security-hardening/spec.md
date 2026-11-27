# 0054 — Backend security hardening

- **Status:** Implemented
- **Area:** ENG, API
- **Owner:** Terry Ong
- **Created:** 2026-11-26
- **Related:** [0012-clearance-sessions](../0012-clearance-sessions/spec.md), [0025-account-settings](../0025-account-settings/spec.md), [0043-rate-limiting-and-client-ip](../0043-rate-limiting-and-client-ip/spec.md), [0045-train-upload-hardening](../0045-train-upload-hardening/spec.md), [0047-auth-flows-and-hardening](../0047-auth-flows-and-hardening/spec.md), [0050-campaign-redesign](../0050-campaign-redesign/spec.md), [0053-frontend-security-hardening](../0053-frontend-security-hardening/spec.md)

## Problem

A security audit of `apps/api` found gaps in error handling, client IP trust, rate limiting, request size bounds, response headers, CSRF defence-in-depth, subprocess isolation, session handling, spend enforcement, and production configuration:

1. **Plaintext password leakage in 422 responses.** `retired_level_is_not_found` delegates all other `RequestValidationError` errors to FastAPI's default handler, which includes `"input"` in the response body. Password fields in `ClearanceRequest`, `PlayerRegisterRequest`, `PlayerLoginRequest`, `AccountPasswordRequest`, `AccountEmailRequest`, `AccountResetRequest`, `AccountDeleteRequest`, and `PlayerResetPasswordRequest` are plain `str`, so validation failures echo plaintext passwords back to clients and logs.
2. **Client IP spoofing.** `client_address()` reads the leftmost address from `TRUSTED_CLIENT_IP_HEADER` (`raw.split(",", 1)[0]`). Behind a proxy that appends the real client IP, a caller can inject a fake IP on the left and bypass all IP rate limits. Also, `client_address()` skips the `x-shield-proxy-secret` check when `TRUSTED_PROXY_SECRET` is unset.
3. **Rate-limit gaps on auth and admin routes.** `POST /auth/confirm` and `POST /auth/reset-password` have no rate limits. `POST /clearance` limits only by IP (no per-email limit) and is not in `botid_paths`. `POST /auth/login` never resets `login_fail` after a valid sign-in. `POST /auth/register` has no per-email throttle.
4. **Unbounded request bodies and nested fields.** `verify_botid` calls `await request.body()` on `/game/train` without streaming limits, which buffers unbounded chunked bodies in memory. `put_saved_board` checks `SAVE_MAX_BYTES` only after Pydantic parses the full JSON payload. `POST /game/run` has no body size cap, and `BoardNodeSchema.config` is an unbounded `dict[str, Any]`.
5. **Missing HTTP security headers and incomplete cache control.** Responses omit `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`, and production `Strict-Transport-Security`. Authenticated endpoints `/game/saves/*`, `/game/progress`, and `/billing/*` omit `Cache-Control: private, no-store`.
6. **Incomplete CSRF defence-in-depth.** Mutating routes accept cookie-authenticated requests without `Origin` or `Sec-Fetch-Site` verification, and the admin `shield_session` cookie uses `SameSite=Lax` instead of `SameSite=Strict`.
7. **Auth flow validation bug in `POST /auth/confirm`.** Neither `POST /auth/confirm` nor `POST /auth/reset-password` checks `flow.purpose`. In `POST /auth/confirm`, when `same_browser` is `False`, `body.confirm` is `True`, `token_hash` is `None`, and `flow` is missing, no verification runs and the route still returns `200 {"status": "confirmed"}`.
8. **Training subprocess secret inheritance and weak signing key checks.** `TrainWorkerRunner` spawns the worker with the full parent environment (exposing `SUPABASE_KEY`, `STRIPE_SECRET_KEY`, LLM keys, `REDIS_URL`, and `TRUSTED_PROXY_SECRET`). `MODEL_SIGNING_KEY` has no minimum length check in production.
9. **Inconsistent mass-assignment protection.** Ten request models in `schemas.py` omit `ConfigDict(extra="forbid")`.
10. **Session rotation, spend race, audit logging, and production guards.** Password change and plan upgrade do not rotate the player session token. `POST /game/run` checks `SpendLedger.ensure_within()` before `run_wave()` and adds cost only after completion (TOCTOU race). Admin and account security events lack structured audit logs. `build_container()` allows `http://` `WEB_BASE_URL`, `SESSION_COOKIE_SECURE=False`, `ALLOW_SELF_UPGRADE=True`, and `redis://` (non-TLS) in production; `Dockerfile` exposes the `Server: uvicorn` header.
11. **Direct backend origin bypass on Vercel.** `ai-shield-backend` is publicly reachable, while `main.py` checks `x-shield-proxy-secret` only on the 9 `botid_paths` `POST` routes. All other routes (`/clearance`, `/auth/account/*`, `/billing/checkout`, `/game/saves/*`, `/game/scores`, `/game/leaderboard*`) can be called directly against the backend URL, bypassing the `apps/web` Nitro proxy, CSRF checks, and Vercel Bot Protection.
12. **Unbounded CSV materialization and Unicode control gaps.** `parse_dataset_csv()` and `parse_custom_dataset()` read all CSV rows into memory before checking `max_rows`, allowing a 1.25 MiB CSV of short rows to allocate hundreds of thousands of rows before rejection. `_clean_training_text()` strips `Cc` but not format (`Cf`) or surrogate (`Cs`) characters.
13. **Supabase config and Docker Compose exposure.** `supabase/config.toml` sets `minimum_password_length = 6` with empty `password_requirements` and leaves `auto_expose_new_tables` unset (defaults to `true`). `compose.yaml` binds unauthenticated Redis to `0.0.0.0:6379`.

## Goals

- Remove raw user input from all 422 validation error responses so passwords and tokens never leak.
- Require `x-shield-proxy-secret` on all production gateway routes except `GET /api/v1/health` and `POST /api/v1/billing/webhook` so direct origin calls are blocked.
- Harden client IP extraction, auth/admin rate limits, and BotID coverage.
- Enforce streaming request body limits before JSON parsing, bound all nested request schemas, and bound CSV row iteration and Unicode sanitization in `packages/engine`.
- Apply baseline security headers, private `no-store` caching, and `Origin`/`Sec-Fetch-Site` CSRF checks on mutating routes.
- Fix `POST /auth/confirm` and `POST /auth/reset-password` flow purpose checks and missing-flow error handling.
- Isolate the training subprocess environment and enforce `MODEL_SIGNING_KEY` minimum strength in production.
- Reject extra fields on all request models, rotate player sessions on password change and upgrade, prevent concurrent spend-cap races, emit structured security audit logs, and tighten production startup, `supabase/config.toml`, and `compose.yaml` guards.

## Non-goals

- Database schema migrations (binding `audit.clearance_sessions` to `admin_user_id` and converting `move_email` to a Postgres RPC are tracked separately).
- Changes to `packages/engine` scoring or classifier models, or replacing `pickle` with `skops.io`.
- Changes to `apps/web` UI or pinning base Docker image SHA256 digests.
- Changing `POST /auth/login` `403` unconfirmed-email UX or `POST /auth/account/email` `409` conflict UX (requires coordinated frontend changes).

## Behaviour

### 1. Validation error sanitization

- Every `RequestValidationError` (422) response strips `"input"` from each error entry and drops raw values from `"ctx"` before returning JSON.
- The existing retired-level 404 override continues to run first.

### 2. Client IP resolution

- `client_address()` returns the socket `peer` whenever `TRUSTED_CLIENT_IP_HEADER` is unset OR `TRUSTED_PROXY_SECRET` is unset or does not match `x-shield-proxy-secret` (constant-time).
- When the header contains a comma-separated list, `client_address()` reads the **rightmost** entry (the hop appended by the trusted proxy) and validates it with `ipaddress.ip_address()`, falling back to `peer` if invalid.

### 3. Auth and admin rate limits and BotID

- `POST /clearance` is added to `botid_paths` in production.
- `POST /clearance` enforces a per-email failure limit (`CLEARANCE_MAX_ATTEMPTS` per `CLEARANCE_WINDOW_MINUTES`) in addition to the existing per-IP limit, and resets both on valid admin sign-in.
- `POST /auth/login` resets `login_fail` for the email on valid sign-in.
- `POST /auth/register` enforces a per-email rate limit (`EMAIL_SEND_LIMIT` per `EMAIL_SEND_WINDOW`) in production.
- `POST /auth/confirm` and `POST /auth/reset-password` enforce `AUTH_IP_LIMIT` per `AUTH_IP_WINDOW` by client IP in production.

### 4. Streaming body size limits and schema bounds

- A middleware enforces streaming body size limits before FastAPI parses JSON, aborting immediately if `Content-Length` or streamed bytes exceed the limit and returning `413`:

| Route | Max body size |
| --- | --- |
| `POST /api/v1/game/train` | `1_310_720` bytes (1.25 MiB) |
| `POST /api/v1/billing/webhook` | `262_144` bytes (256 KiB) |
| All other `POST`, `PUT`, `PATCH`, `DELETE` routes | `262_144` bytes (256 KiB) |

- Request schemas enforce strict bounds:
  - All request models set `ConfigDict(extra="forbid")`.
  - `BoardNodeSchema.id`, `BoardEdgeSchema.id`, `source`, `target` have `max_length=128`.
  - `BoardNodeSchema.config` is bounded (at most 32 keys, max nesting depth 4, serialized JSON size at most 16 KiB).
  - `SavedBoardRequest.positions` has `max_length=60`.
  - `GameTrainRequest.csv_text` has `max_length=1_310_720`; `dataset` has `max_length=2000`; `TrainingRowSchema.text` has `max_length=4000`.

### 5. Security response headers and cache control

- Every HTTP response sets:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`
  - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`
  - In production (`APP_ENV == "production"`): `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- Responses for `/api/v1/auth/*`, `/api/v1/clearance`, `/api/v1/game/saves/*`, `/api/v1/game/progress`, `/api/v1/game/leaderboard/me`, and `/api/v1/billing/*` (excluding `/webhook`) set `Cache-Control: private, no-store`.

### 6. CSRF origin verification and strict admin cookie

- For `POST`, `PUT`, `PATCH`, and `DELETE` requests (except `/api/v1/billing/webhook`):
  - If `Sec-Fetch-Site` is present and not in `{"same-origin", "none"}`, return `403 {"detail": "Cross-site request blocked."}`.
  - If `Origin` is present and not in `settings.CORS_ORIGINS`, return `403 {"detail": "Cross-site request blocked."}`.
  - In production, if a request carries a session cookie (`shield_session` or `shield_player_session`) and both `Origin` and `Sec-Fetch-Site` are absent, return `403 {"detail": "Cross-site request blocked."}`.
- `POST /clearance` and `DELETE /clearance` set `samesite="strict"` on the `shield_session` cookie.

### 7. Auth flow purpose and verification completeness

- `POST /auth/confirm` requires `flow.purpose in {"signup", "email_change"}` (matching `body.type`) whenever `flow` is loaded; mismatched purpose is treated as no matching flow.
- `POST /auth/reset-password` requires `flow.purpose == "recovery"` whenever `flow` is loaded; mismatched purpose does not supply `code_verifier`.
- In `POST /auth/confirm`, when `same_browser` is `False` and `body.confirm` is `True`, if neither `body.token_hash` nor `(body.code and flow and flow.code_verifier)` is available to verify, the endpoint returns `400` (`CONFIRM_INVALID`) instead of `200 {"status": "confirmed"}`.

### 8. Subprocess isolation and signing key strength

- `TrainWorkerRunner` spawns the worker with an explicit allowlisted `env` (`PATH`, `PYTHONPATH`, `PYTHONUNBUFFERED`, `HOME`, `TMPDIR`, `LANG`) so parent secrets are never passed to the child process.
- In production (`APP_ENV == "production"`), if `MODEL_SIGNING_KEY` is set with fewer than 32 UTF-8 bytes, `resolve_model_signing_key()` treats it as invalid (`None`) and logs an error.

### 9. Session rotation and spend concurrency

- `POST /auth/account/password` issues a fresh session token for the caller, sets the new `shield_player_session` cookie, and revokes all prior sessions (including the old current token).
- `POST /auth/upgrade` rotates the caller's session token and sets the updated `shield_player_session` cookie.
- `POST /game/run` prevents concurrent wave runs for the same spend owner from bypassing `SpendLedger.ensure_within()` by holding a per-owner concurrency lock (or atomic spend reservation) across quota-counted runs.

### 10. Audit logging and production configuration guards

- Emit structured `INFO`/`WARNING` audit log records (event name, redacted actor/email hash, client IP, outcome; never passwords or raw tokens) for: admin clearance grant/deny, `DELETE /game/scores`, password change/reset, email change, and account deletion.
- In `build_container()` when `APP_ENV == "production"`, fail startup with `ConfigurationError` if:
  - `WEB_BASE_URL` scheme is not `https`,
  - `SESSION_COOKIE_SECURE` is `False`,
  - `ALLOW_SELF_UPGRADE` is `True`, or
  - `REDIS_URL` does not use `rediss://` (unless an explicit opt-out is not set — require `rediss://` in production).
- `apps/api/Dockerfile` passes `--no-server-header` to `uvicorn`.

### 11. Direct-origin proxy secret enforcement

- In production (`APP_ENV == "production"`), every request to `apps/api` (all HTTP methods and paths) **except** `GET /api/v1/health` and `POST /api/v1/billing/webhook` must present an `x-shield-proxy-secret` header matching `TRUSTED_PROXY_SECRET` (constant-time comparison).
- Requests missing or failing this header receive `403 {"detail": "Request blocked."}` before reaching route handlers.
- Routes in `botid_paths` continue to additionally require `x-shield-botid: pass`.

### 12. Bounded CSV parsing and Unicode sanitization (`packages/engine`)

- `parse_dataset_csv()` and `parse_custom_dataset()` cap CSV iteration (for example `itertools.islice(reader, max_rows + 2)`) and raise `BoardValidationError` immediately when rows exceed `max_rows`, without materializing the full CSV in memory.
- `_clean_training_text()` strips format (`Cf`) and surrogate (`Cs`) Unicode characters in addition to control (`Cc`) characters.

### 13. Supabase config, Docker Compose, and operational hardening

- `supabase/config.toml` sets `auto_expose_new_tables = false` under `[api]`, and sets `minimum_password_length = 8` and `password_requirements = "lower_upper_letters_digits"` under `[auth]` and `[remotes.production.auth]`.
- `compose.yaml` binds Redis to loopback (`127.0.0.1:6379:6379`) instead of `0.0.0.0:6379`.
- Operational toggles (tracked in `tasks.md` outside automated tests): enable Supabase Leaked Password Protection and DB SSL enforcement; switch Vercel `ai-shield` Bot Protection from `Log` to `Challenge`; add a Vercel Firewall custom rule on `ai-shield-backend` blocking non-health/non-webhook traffic without `x-shield-proxy-secret`; remove the unused `STRIPE_API_KEY` production env var from `ai-shield-backend`.

## Acceptance criteria

- **API-SEC-001**: Given an invalid password or body submitted to `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/account/password`, or `POST /api/v1/clearance`, when FastAPI returns `422`, then the response body does not contain `"input"` and does not contain the submitted password string.
- **API-SEC-002**: Given `TRUSTED_CLIENT_IP_HEADER` is configured, when `TRUSTED_PROXY_SECRET` is unset or does not match `x-shield-proxy-secret`, then `client_address()` returns the socket peer address; and when the secret matches and the header contains `"198.51.100.1, 203.0.113.9"`, then `client_address()` returns `"203.0.113.9"`.
- **API-SEC-003**: Given `APP_ENV="production"`, when requests exceed the limit on `POST /api/v1/auth/confirm`, `POST /api/v1/auth/reset-password`, or per-email `POST /api/v1/auth/register` or `POST /api/v1/clearance`, then the gateway returns `429`; `POST /api/v1/clearance` without valid BotID headers returns `403`; and a valid `POST /api/v1/auth/login` resets `login_fail` for that email.
- **API-SEC-004**: Given a `POST` or `PUT` request whose streamed body exceeds the route limit (256 KiB default, 1.25 MiB on `/api/v1/game/train`) even without a `Content-Length` header, when the gateway handles the request, then it returns `413` before JSON parsing; and given a `BoardNodeSchema.config` exceeding 32 keys, depth 4, or 16 KiB, then the gateway returns `422`.
- **API-SEC-005**: Given any response from the API, then it includes `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`; production responses also include `Strict-Transport-Security`; and authenticated responses for `/api/v1/game/saves/{level_id}`, `/api/v1/game/progress`, and `/api/v1/billing/sync` include `Cache-Control: private, no-store`.
- **API-SEC-006**: Given a `POST`, `PUT`, `PATCH`, or `DELETE` request (other than `/api/v1/billing/webhook`) with `Sec-Fetch-Site: cross-site`, `Sec-Fetch-Site: same-site`, an `Origin` not in `CORS_ORIGINS`, or in production with a session cookie and neither `Origin` nor `Sec-Fetch-Site`, then the gateway returns `403`; and `POST /api/v1/clearance` sets `SameSite=Strict` on `shield_session`.
- **API-SEC-007**: Given `POST /api/v1/auth/confirm` with `same_browser=False`, `confirm=True`, `code="abc"`, `token_hash=None`, and a missing or mismatched-purpose `flow_id`, then the gateway returns `400` instead of `200`; and `POST /api/v1/auth/reset-password` ignores a `flow_id` whose `purpose` is not `"recovery"`.
- **API-SEC-008**: Given `TrainWorkerRunner` starts a training subprocess when parent `os.environ` contains secrets (`SUPABASE_KEY`, `STRIPE_SECRET_KEY`, `GOOGLE_API_KEY`), then those environment variables are absent in the child process; and given `APP_ENV="production"` with a `MODEL_SIGNING_KEY` shorter than 32 bytes, then `resolve_model_signing_key()` returns `None`.
- **API-SEC-009**: Given an unrecognized extra JSON field sent to `ClearanceRequest`, `PlayerRegisterRequest`, `PlayerLoginRequest`, `PlayerResendRequest`, `PlayerRecoverRequest`, `GameRunRequest`, `BoardNodeSchema`, `BoardEdgeSchema`, `BoardGraphSchema`, or `AgentToolSchema`, then the gateway returns `422`.
- **API-SEC-010**: Given a signed-in player calls `POST /api/v1/auth/account/password` or `POST /api/v1/auth/upgrade`, then the response sets a new `shield_player_session` cookie token and the previous session token is revoked.
- **API-SEC-011**: Given two concurrent `POST /api/v1/game/run` requests for the same spend owner whose combined cost exceeds the daily provider budget, when both execute, then the second request observes the first run's spend (or is serialized) and is rejected with `429` once the budget is reached.
- **API-SEC-012**: Given `APP_ENV="production"`, when `build_container()` runs with `WEB_BASE_URL="http://..."`, `SESSION_COOKIE_SECURE=False`, `ALLOW_SELF_UPGRADE=True`, or `REDIS_URL="redis://..."`, then it raises `ConfigurationError`; admin clearance grant/deny and `DELETE /api/v1/game/scores` emit structured audit log entries without credentials; and `apps/api/Dockerfile` includes `--no-server-header`.
- **API-SEC-013**: Given `APP_ENV="production"`, when any request other than `GET /api/v1/health` or `POST /api/v1/billing/webhook` (for example `GET /api/v1/game/scores`, `GET /api/v1/game/levels`, `POST /api/v1/clearance`, or `PUT /api/v1/game/saves/easy-1`) omits or presents a wrong `x-shield-proxy-secret` header, then the gateway returns `403 {"detail": "Request blocked."}`; `GET /api/v1/health` and `POST /api/v1/billing/webhook` remain reachable without that header.
- **API-SEC-014**: Given `supabase/config.toml` and `compose.yaml`, then `supabase/config.toml` sets `auto_expose_new_tables = false`, `minimum_password_length = 8`, and `password_requirements = "lower_upper_letters_digits"`, and `compose.yaml` binds Redis port `6379` to `127.0.0.1` rather than all interfaces.
- **ENG-SEC-001**: Given a CSV with more than `max_rows` rows passed to `parse_dataset_csv()` or `parse_custom_dataset()`, then parsing stops at `max_rows + 2` rows and raises `BoardValidationError`; and given training text containing Unicode format (`Cf`, such as `\u200b` or `\u202e`) or surrogate characters, then `_clean_training_text()` removes them.

## Changes to earlier criteria

| Earlier criterion | Spec | Changed by | Change |
| --- | --- | --- | --- |
| API-IP-002 | 0043 | API-SEC-002 | Without `TRUSTED_PROXY_SECRET`, the trusted IP header is ignored; with it, the last entry is read |
| API-RATE-004 | 0043 | API-SEC-003 | A valid sign-in resets the failed-login count for that email |
| API-IP-005 | 0043 | API-SEC-003 | Clearance failures also count per email, so one email is limited from any address |
| API-BOTID-005 | 0043 | API-SEC-013 | Unprotected routes need no BotID header, but production needs the proxy secret on every route |
| API-DOCS-001 | 0007 | API-SEC-013 | In production the gateway answers `403` without the proxy secret; with it, the docs routes are `404` |
| API-AUTH-015 | 0047 | API-SEC-005 | Auth and clearance responses are `private, no-store` |
| API-CLEAR (cookie) | 0028 | API-SEC-006 | `shield_session` is `SameSite=Strict` |
| API-TRAIN-022 | 0045 | API-SEC-010 | A password change rotates the caller's session too; its trained model moves to the new token |

## Decisions (2026-11-27)

- The `Origin` allowlist is `CORS_ORIGINS` plus the origin of `WEB_BASE_URL`, so the production web origin passes even when `CORS_ORIGINS` lists only local hosts.
- A request that proves the proxy secret skips the `Origin` allowlist: the web proxy already refused any `Origin` that is not its own page (WEB-SEC-006). Vercel preview deployments have their own origins, so they would be refused otherwise (code review, 2026-11-27).
- `POST /api/v1/clearance` is in the web proxy's BotID route list too, so the proxy sends the BotID pass that the gateway requires.
- A run holds a per-owner lock only when it counts toward the quota; a model-free Easy run has no spend, so it never waits.
- When a session rotates, its trained model is verified and signed again for the new token (`TrainedModelStore.move_session`).

## Security & privacy considerations

- **Fail-closed defaults:** Client IP parsing, CSRF checks, body-size streaming, auth flow purpose checks, and production configuration checks all fail closed.
- **No secret leakage:** Sanitized 422 handlers, allowlisted subprocess `env`, and structured audit logs ensure passwords, API keys, and raw session tokens never appear in responses, child processes, or logs.
- **Contract compatibility:** Adding `extra="forbid"` and tightening `max_length` constraints may update `contracts/shield-api.openapi.json`; run `mise run contract` after schema edits.

## Evaluation impact

None. No engine scoring or classifier change.

## Open questions

None.

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: API-SEC-001, API-SEC-002, API-SEC-003, API-SEC-004, API-SEC-005, API-SEC-006, API-SEC-007, API-SEC-008, API-SEC-009, API-SEC-010, API-SEC-011, API-SEC-012, API-SEC-013, API-SEC-014, ENG-SEC-001
- Red: 17 failing test(s) before implementation (`apps/api/tests/test_backend_security.py`, `apps/api/tests/test_backend_security.py`, `apps/api/tests/test_backend_security.py`)
- Green: 28 passing test(s)
- Gate: `mise run check` passed

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: API-SEC-006
- Red: 1 failing test(s) before implementation (`apps/api/tests/test_backend_security.py::test_a_proxied_preview_origin_is_allowed`)
- Green: 3 passing test(s)
- Gate: `mise run check` passed
