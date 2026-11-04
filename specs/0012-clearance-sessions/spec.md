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

- User accounts, roles or SSO. There is still one shared admin passphrase
  (`SECURE_PASSPHRASE`).
- Sessions on Supabase. Sessions always live in the gateway's SQLite file
  (`SQLITE_PATH`), even when the audit log uses Supabase. A multi-instance
  deployment would need a shared session store; that is out of scope.
- Changing how the engine uses `Clearance`.

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

- **API-CLEAR-001**: Given the correct passphrase, when `POST /clearance` is called, then it returns `200` with `granted=true` and an `expires_at` equal to now + `SESSION_TTL_MINUTES`, and sets an `HttpOnly`, `SameSite=Lax`, `Path=/api/v1` cookie named `shield_session`.
- **API-CLEAR-002**: Given a wrong passphrase, or `SECURE_PASSPHRASE` unset, when `POST /clearance` is called, then it returns `401` with the same generic `detail` in both cases and sets no cookie.
- **API-CLEAR-003**: After any clearance request (granted or not), neither the passphrase nor the raw token appears in the SQLite file, the audit log or the captured log output; the `sessions` table holds only the token's SHA-256 hash.
- **API-CLEAR-004**: Given a valid session cookie, when `/chat` or `/screen` runs, then the engine receives `Clearance.GRANTED`; with no cookie, or an unknown, expired or revoked cookie, it receives `Clearance.NONE`. (Supersedes API-CHAT-003.)
- **API-CLEAR-005**: Given a live session, when `DELETE /clearance` is called, then it returns `204`, the session row is gone, the response expires the cookie, and a later `/chat` with the old cookie gets `Clearance.NONE`. Calling it with no session also returns `204`.
- **API-CLEAR-006**: `GET /clearance` returns `granted=true` with `expires_at` for a live session, and `granted=false, expires_at=null` otherwise.
- **API-CLEAR-007**: Given a session written by one `SqliteSessionStore`, when a new instance opens the same file, then the session is still valid; expired rows are deleted whenever a new session is created.
- **API-CLEAR-008**: Given `CLEARANCE_MAX_ATTEMPTS` failed attempts from one client address inside `CLEARANCE_WINDOW_MINUTES`, when another attempt is made (even with the correct passphrase), then it returns `429` with a `Retry-After` header; a successful grant resets the counter.
- **API-CLEAR-009**: `ChatRequest` and `ScreenRequest` have no `passphrase` field, audit metadata has `clearance` in place of `passphrase_provided`, and the committed OpenAPI contract and `api.gen.ts` match (API-CONTRACT-001 still holds).
- **API-CLEAR-010**: Given a preflight from an origin in `CORS_ORIGINS`, when it asks for `DELETE` with credentials, then the response allows the method and returns `Access-Control-Allow-Credentials: true`; given an origin not in the list, then no CORS allow headers are returned.
- **API-CLEAR-011**: Given a failed `POST /clearance` from a client address and no live session, when that address calls `/chat` or `/screen` inside `CLEARANCE_WINDOW_MINUTES`, then the engine receives `Clearance.DENIED`; after the window, it receives `Clearance.NONE`.
- **API-CLEAR-012**: Given `CORS_ORIGINS` contains `*`, when the app is created, then startup fails with a configuration error.
- **API-CLEAR-013**: Given the session store raises during lookup, when `/chat` or `/screen` runs, then the engine receives `Clearance.NONE`, the error is logged with `logger.exception`, and the chat stream completes normally.

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
