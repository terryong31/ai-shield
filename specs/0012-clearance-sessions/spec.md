# 0012 — Clearance sessions

- **Status:** Implemented
- **Area:** API
- **Owner:** Terry Ong
- **Created:** 2026-09-24
- **Related:** spec 0007 (supersedes API-CHAT-003), spec 0009, spec 0011 (WEB-CLEAR-001), [plan.md](plan.md), [tasks.md](tasks.md)

## Problem

To use admin tools, the web client sends the raw passphrase with **every**
`/chat` request. To do that, it keeps the passphrase in plaintext in
`localStorage` (`apps/web/app/composables/usePassphrase.ts`), where any
script on the origin can read it and where it survives indefinitely. There
is no expiry, no way to revoke access on the server, and no limit on guessing.

## Goals

- The passphrase crosses the network **once**, when access is granted, and is
  never stored anywhere: not in the browser, the database or the logs.
- The browser holds only an opaque session cookie that scripts cannot read.
- Sessions expire, can be revoked, and survive a gateway restart.
- Repeated wrong passphrases are rate-limited.
- The engine still sees only a `Clearance` value (architecture rule
  "Credentials stop at the gateway").

## Non-goals

- SSO or a second factor for admins. (The shared `SECURE_PASSPHRASE` is
  replaced by per-admin Supabase accounts; see "Admin accounts" below.)
- Changing how the engine uses `Clearance`.

## Admin accounts (2026-11-09)

**Problem.** `POST /clearance` fell back to `sign_in_with_password` and granted
admin to **any** Supabase Auth user. Every player registration also creates a
Supabase Auth user (the best-effort mirror in `routers/auth.py`), so any
player could open `/_console` and clear the scoreboard with their own
credentials. The shared `SECURE_PASSPHRASE` also cannot tell admins apart or
remove one without rotating it for everyone.

**Change.** The same model as the nego-lah console:

- An admin is an ordinary Supabase Auth user whose **`app_metadata.role` is
  `"admin"`**. `app_metadata` is writable only with the service key, so a user
  cannot grant it to themselves. `user_metadata` is user-writable and is never
  trusted.
- `POST /clearance` takes `{ "email", "password" }`. The gateway signs in with
  a throwaway Supabase client, checks the role, signs that Supabase session
  out, and then opens the same opaque `shield_session` as before. Every failure
  gets the same generic `401`.
- `SECURE_PASSPHRASE` is removed. Without Supabase configured, nobody can
  obtain clearance.
- Admins are created and revoked with a script:
  `mise run admin:create <email>` (prompts for the password; creates the user
  with a confirmed email, or updates an existing user's password, and merges
  `role: "admin"` into `app_metadata`) and `mise run admin:revoke <email>`.
- Revoking the role stops new sign-ins. A session already open lasts until it
  expires (`SESSION_TTL_MINUTES`) or is revoked with `DELETE /clearance`.

## Behaviour

### Endpoints

| Method and path | Body | Success | Failure |
| --- | --- | --- | --- |
| `POST /api/v1/clearance` | `{ "passphrase": string }` | `200 ClearanceStatus`, and sets the cookie | `401` generic `detail`, no cookie; `429` with `Retry-After` when rate-limited |
| `GET /api/v1/clearance` | none | `200 ClearanceStatus` (granted or not) | none |
| `DELETE /api/v1/clearance` | none | `204`, deletes the session row and expires the cookie | none (idempotent) |

`ClearanceStatus = { granted: boolean, expires_at: datetime | null }`

### Cookie

`shield_session=<token>; HttpOnly; SameSite=Lax; Path=/api/v1; Max-Age=<ttl>`,
plus `Secure` when `SESSION_COOKIE_SECURE` is true. The token is 32 random
bytes (URL-safe). Only its SHA-256 hash is stored.

### Clearance on `/chat` and `/screen`

| Request carries | Clearance passed to the engine |
| --- | --- |
| no cookie | `NONE` |
| a cookie for a live session | `GRANTED` |
| a cookie that is unknown, expired or revoked | `NONE` |
| no live session, and a failed `POST /clearance` from the same client address inside the rate-limit window | `DENIED` |

The last row keeps today's defence in depth: someone caught guessing the
passphrase gets `DENIED`, which the engine treats more strictly than `NONE`
(mandatory adjudication and a tool lockout, ENG-PIPE-007 and ENG-PIPE-009).

The client address is `request.client.host`. `X-Forwarded-For` and similar
headers are ignored, because they are client-controlled. Deployments behind a
proxy must run uvicorn with `--proxy-headers` and trusted `--forwarded-allow-ips`.

The `passphrase` field is **removed** from `ChatRequest` and `ScreenRequest`
(a breaking contract change).
Scripts that call `/screen` now obtain clearance the same way, by calling
`POST /clearance` first and sending the cookie. Audit metadata records `clearance`
(`"NONE"`, `"GRANTED"` or `"DENIED"`) in place of `passphrase_provided`.

### Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `SESSION_TTL_MINUTES` | `480` | Absolute session lifetime |
| `SESSION_COOKIE_SECURE` | `true` | Adds `Secure`. Browsers accept it on `http://localhost`; set it to `false` only for other plain-HTTP hosts |
| `CLEARANCE_MAX_ATTEMPTS` | `5` | Failed attempts allowed per client address in the window |
| `CLEARANCE_WINDOW_MINUTES` | `10` | Rate-limit window |

## Acceptance criteria

- **API-CLEAR-014**: Given a Supabase Auth user whose `app_metadata.role` is `"admin"`, when `POST /clearance` is called with that user's `email` and `password`, then it returns `200` with `granted=true` and an `expires_at` equal to now + `SESSION_TTL_MINUTES`, and sets an `HttpOnly`, `SameSite=Lax`, `Path=/api/v1` cookie named `shield_session`.
- **API-CLEAR-015**: Given a wrong password, an unknown email, a user without `app_metadata.role = "admin"` (including a registered player, and a user whose `user_metadata.role` is `"admin"`), or a Supabase Auth error, when `POST /clearance` is called, then it returns `401` with the same generic `detail` in every case and sets no cookie.
- **API-CLEAR-016**: After any clearance request (granted or not), neither the password nor the raw token appears in any stored row or the captured log output, the sessions table holds only the token's SHA-256 hash, and every Supabase Auth session opened to check a password has been signed out.
- **API-CLEAR-017**: Given `CLEARANCE_MAX_ATTEMPTS` failed attempts from one client address inside `CLEARANCE_WINDOW_MINUTES`, when another attempt is made (even with an admin's correct credentials), then it returns `429` with a `Retry-After` header without calling Supabase Auth; a successful grant resets the counter, and the limit lifts after the window.
- **API-CLEAR-018**: `Settings` has no `SECURE_PASSPHRASE`; `POST /clearance` with only a `passphrase` returns `422`; the committed contract's `ClearanceRequest` has exactly the required properties `email` and `password`.
- **API-CLEAR-019**: Given `admin:create <email>` and a password read from a prompt, when no Supabase Auth user has that email (matched case-insensitively), then one is created with `email_confirm=true` and `app_metadata.role="admin"`; when one exists, its password is updated, its email confirmed, and `role="admin"` merged into its existing `app_metadata`. `admin:revoke <email>` removes `role` and keeps the other `app_metadata` keys. An unknown email on revoke, or an empty password, exits non-zero without writing. The password is never taken from the command line or printed.
- **WEB-CLEAR-002**: The console sign-in form sends `email` and `password` once to `POST /clearance`; the browser stores neither, and no console text mentions a passphrase.
- **API-CLEAR-005**: Given a live session, when `DELETE /clearance` is called, then it returns `204`, the session row is gone, the response expires the cookie, and a later `/chat` with the old cookie gets `Clearance.NONE`. Calling it with no session also returns `204`.
- **API-CLEAR-006**: `GET /clearance` returns `granted=true` with `expires_at` for a live session, and `granted=false, expires_at=null` otherwise.
- ~~API-CLEAR-007~~ (retired by spec 0046): clearance sessions are stored only in Supabase `audit.clearance_sessions`; durability across restarts is Postgres's.
- **API-CLEAR-010**: Given a preflight from an origin in `CORS_ORIGINS`, when it asks for `DELETE` with credentials, then the response allows the method and returns `Access-Control-Allow-Credentials: true`; given an origin not in the list, then no CORS allow headers are returned.
- **API-CLEAR-012**: Given `CORS_ORIGINS` contains `*`, when the app is created, then startup fails with a configuration error.

## Security & privacy considerations

- **Before:** a long-lived plaintext secret in `localStorage`, sent on every
  request. **After:** a short-lived, revocable, `HttpOnly` token whose
  database copy is only a hash, so a leaked database cannot be replayed.
- **CSRF:** `SameSite=Lax` stops cross-site `POST`s from carrying the cookie.
  JSON bodies force a CORS preflight, which only `CORS_ORIGINS` pass. The
  web client and gateway on different `localhost` ports are the same site,
  so the cookie is still sent.
- **Guessing:** limited by API-CLEAR-008. The passphrase is compared with
  `hmac.compare_digest`, as today.
- **Fail-closed:** any session-store error resolves to `Clearance.NONE`, is
  logged with `logger.exception`, and never fails the chat stream.
- **Engine:** unchanged. It still receives only a `Clearance`, and the
  `DENIED` path stays reachable (API-CLEAR-011).
- **Superseded criterion:** API-CHAT-003 in spec 0007 is retired as part of
  this cycle. Its line is rewritten exactly as
  `- ~~API-CHAT-003~~ Retired 2026-09-24: superseded by API-CLEAR-004 and API-CLEAR-011 (spec 0012).`
  Without the `- **ID**` prefix, `spec:check` no longer requires a test for it,
  and its old test in `test_chat.py` is replaced by the API-CLEAR-004 and 011 tests.
  Accepting this spec approves that edit to spec 0007.

## Evaluation impact

None. No engine change.

## Open questions

None.

## Retired by 0026

Clearance no longer reaches an engine pipeline. It gates the admin console and `DELETE /api/v1/game/scores`; the equivalent behaviour (granted, none, denied after a failed guess, fail-closed store errors) is tested under API-CLEAN-003.

- `API-CLEAR-004`: Given a valid session cookie, when `/chat` or `/screen` runs, then the engine receives `Clearance.GRANTED`; with no cookie, or an unknown, expired or revoked cookie, it receives `Clearance.NONE`. (Supersedes API-CHAT-003.)
- `API-CLEAR-009`: `ChatRequest` and `ScreenRequest` have no `passphrase` field, audit metadata has `clearance` in place of `passphrase_provided`, and the committed OpenAPI contract and `api.gen.ts` match (API-CONTRACT-001 still holds).
- `API-CLEAR-011`: Given a failed `POST /clearance` from a client address and no live session, when that address calls `/chat` or `/screen` inside `CLEARANCE_WINDOW_MINUTES`, then the engine receives `Clearance.DENIED`; after the window, it receives `Clearance.NONE`.
- `API-CLEAR-013`: Given the session store raises during lookup, when `/chat` or `/screen` runs, then the engine receives `Clearance.NONE`, the error is logged with `logger.exception`, and the chat stream completes normally.

## Retired by admin accounts (2026-11-09)

Replaced by API-CLEAR-014 to 018 when `SECURE_PASSPHRASE` gave way to Supabase admin accounts.

- `API-CLEAR-001`: Given the correct passphrase, when `POST /clearance` is called, then it returns `200` with `granted=true` and an `expires_at` equal to now + `SESSION_TTL_MINUTES`, and sets an `HttpOnly`, `SameSite=Lax`, `Path=/api/v1` cookie named `shield_session`. (Now API-CLEAR-014.)
- `API-CLEAR-002`: Given a wrong passphrase, or `SECURE_PASSPHRASE` unset, when `POST /clearance` is called, then it returns `401` with the same generic `detail` in both cases and sets no cookie. (Now API-CLEAR-015.)
- `API-CLEAR-003`: After any clearance request (granted or not), neither the passphrase nor the raw token appears in the SQLite file, the audit log or the captured log output; the `sessions` table holds only the token's SHA-256 hash. (Now API-CLEAR-016.)
- `API-CLEAR-008`: Given `CLEARANCE_MAX_ATTEMPTS` failed attempts from one client address inside `CLEARANCE_WINDOW_MINUTES`, when another attempt is made (even with the correct passphrase), then it returns `429` with a `Retry-After` header; a successful grant resets the counter. (Now API-CLEAR-017.)

## Verification

### 2026-09-24 · commit 489ecc5 (+ uncommitted changes)

- Criteria: API-CLEAR-001, API-CLEAR-002, API-CLEAR-003, API-CLEAR-004, API-CLEAR-005, API-CLEAR-006, API-CLEAR-007, API-CLEAR-008, API-CLEAR-009, API-CLEAR-010, API-CLEAR-011, API-CLEAR-012, API-CLEAR-013
- Red: 13 failing test(s) before implementation (`apps/api/tests/test_clearance.py`, `apps/api/tests/test_clearance.py`, `apps/api/tests/test_clearance.py`)
- Green: 19 passing test(s)
- Gate: `mise run check` passed

### 2026-10-30 · commit 489ecc5 (+ uncommitted changes)

- Criteria: API-CLEAR-010
- Red: 3 failing test(s) before implementation (`apps/api/tests/test_clearance.py::test_cors_allows_credentialed_delete_only_for_known_origins[http://127.0.0.1:3000]`, `apps/api/tests/test_clearance.py::test_cors_allows_credentialed_delete_only_for_known_origins[http://[::1]:3000]`, `apps/api/tests/test_clearance.py::test_cors_allows_credentialed_delete_only_for_known_origins[http://[::]:3000]`)
- Green: 4 passing test(s)
- Gate: `mise run check` passed

### 2026-11-09 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-CLEAR-014, API-CLEAR-015, API-CLEAR-016, API-CLEAR-017, API-CLEAR-018, API-CLEAR-019, WEB-CLEAR-002
- Red: 7 failing test(s) before implementation (`apps/api/tests/test_clearance.py`, `apps/api/tests/test_clearance.py`, `apps/api/tests/test_clearance.py`)
- Green: 20 passing test(s)
- Gate: `mise run check` passed
