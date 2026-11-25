# 0043 — Rate limiting, trusted client IP, bot protection and production configuration

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-23
- **Related:** [0012-clearance-sessions](../0012-clearance-sessions/spec.md) (`AttemptLimiter`), [0041-same-origin-api-proxy](../0041-same-origin-api-proxy/spec.md) (WEB-PROXY-010), [0042](../0042-run-spend-and-account-integrity/spec.md) (anonymous quota), [0045](../0045-train-upload-hardening/spec.md) (`/game/train`), [Vercel BotID get started](https://vercel.com/docs/botid/get-started)

## Problem

Apart from the admin `AttemptLimiter` on `POST /clearance`, the gateway has no
rate limiting. `/game/run` (model calls), `/auth/anonymous` (session minting),
`/auth/register`, `/auth/login` (password guessing), `/game/train` (CPU), `/auth/recover` and
`/auth/resend-confirmation` (email sending through Supabase) can be called as
fast as a client likes.

Client IP is also wrong in production: `dependencies.client_address` trusts
only the socket peer. Behind the same-origin Nuxt proxy (spec 0041) and Vercel
every request comes from the proxy, so all players share one IP, and the proxy
deliberately strips `X-Forwarded-*` (WEB-PROXY-010).

## Goals

- A small fixed-window limiter in the gateway, per client IP and per account
  or email where relevant, shared across instances through Redis when
  `REDIS_URL` is set, in-memory otherwise.
- A real client IP behind the Nuxt proxy / Vercel that a direct caller cannot
  spoof.
- `429` with `Retry-After` when limited.
- Bots cannot mint anonymous sessions, sign up, sign in, run or train in bulk:
  Vercel BotID verifies those requests in the Nuxt proxy, and the gateway
  refuses them unless the proxy vouches for them. This replaces a per-IP daily
  anonymous run cap (dropped from spec 0042).

## Non-goals

- New dependencies (no `slowapi`, `limits`). Uses `redis` (already installed) or memory.
- Replacing the admin `AttemptLimiter`.
- Edge/WAF rules (Vercel firewall); documented as complementary only.
- `/game/train` validation and its daily cap (spec 0045); only its per-minute limit is here.

## Behaviour

### Limits (fixed window, production constants)

| Route(s) | Bucket key | Limit | Counts |
| --- | --- | --- | --- |
| `/auth/login`, `/auth/register`, `/auth/recover`, `/auth/resend-confirmation` | client IP (one shared `auth` bucket) | 30 / 5 minutes | every request |
| `/auth/login` | normalised account email | 10 / 15 minutes | **failed** logins only (`401` / `403`) |
| `/auth/anonymous` | client IP | 30 / hour | every request |
| `/auth/recover` | normalised email | 1 / 60 seconds | every request |
| `/auth/resend-confirmation` | normalised email | 1 / 60 seconds | every request |
| `/game/run` | client IP | 30 / minute | every request |
| `/game/run` | account email, or hashed anonymous session | 10 / minute | every request |
| `/game/train` | account email | 10 / minute | every request (daily cap is spec 0045) |

- Request-counted buckets are checked and incremented before the handler runs,
  so a limited request makes no model, Supabase or email call.
- The failed-login bucket is checked before the password is verified and
  incremented only after a failure. While it is full, every login for that
  email (correct password or not) answers `429` with `Retry-After`; the window
  expires on its own, so the account is never locked out permanently and no
  admin action is needed. A success does not reset the counter.
- `/auth/recover` and `/auth/resend-confirmation` give the same answer for known
  and unknown addresses, both when allowed (`200`/`202`) and when limited
  (`429`).

**On/off.** The limiter is on exactly when `APP_ENV == "production"` (the
existing setting; default `production`, `mise run api:dev` sets
`development`). There is no separate `RATE_LIMIT_ENABLED` setting: local
development has no limits, production uses the fixed constants above. The
constants live in `services/rate_limit.py` and are documented in
`docs/reference/configuration.md` next to `APP_ENV`.

Limited answers:

```
HTTP/1.1 429 Too Many Requests
Retry-After: <seconds until the window resets, integer >= 1>
{"detail": "Too many requests. Try again in <n> seconds."}
```

Keys are stored hashed (`rl:<bucket>:<sha256(key)>:<window>`); raw IPs and
emails are never written to Redis or logged.

### Sources

- Supabase Auth rate limits (hosted defaults: `sign_in_sign_ups` 30 per 5
  minutes per IP, `anonymous_users` 30 per hour per IP, OTP / magic-link and
  recovery emails once per 60 seconds per user):
  https://supabase.com/docs/guides/auth/rate-limits
- OWASP ASVS V2 (Authentication): anti-automation must allow no more than 100
  failed attempts per hour on a single account; 10 per 15 minutes (≤ 40 per
  hour) is well below that.
- OWASP Authentication Cheat Sheet: throttle login attempts without creating
  an account-lockout denial-of-service (hence a time window, not a lock).
- `/game/run` and `/game/train` have no external standard; the numbers are set
  by model and CPU cost.

### Backends

- `REDIS_URL` set: `INCR` + `EXPIRE` on the window key, reusing the container's
  Redis client. If Redis errors, the limiter falls back to the in-memory
  counter for that request and logs a warning (fail to a local limit, not
  open and not closed).
- Otherwise: an in-process dict of `(key, window) → count`, pruned of expired
  windows.

### Client IP

New gateway settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `TRUSTED_CLIENT_IP_HEADER` | unset | Header to read the client IP from (first comma-separated entry), e.g. `x-shield-client-ip`, `x-vercel-forwarded-for`, `x-real-ip`. Unset: socket peer only (today). |
| `TRUSTED_PROXY_SECRET` | unset | When set, the header above is honoured only if the request carries `x-shield-proxy-secret` equal to it (constant-time compare); otherwise the socket peer is used. |

`client_address()` uses these for every caller, including the admin
`AttemptLimiter`. A malformed header value (not an
IPv4/IPv6 address) falls back to the socket peer.

Nuxt proxy (`shared/utils/apiProxy.ts` + the server route):

- New server-only runtime config `apiProxySecret` (`NUXT_API_PROXY_SECRET`) and
  `clientIpHeader` (`NUXT_CLIENT_IP_HEADER`, defaulting to
  `'x-vercel-forwarded-for'` in `nuxt.config.ts`).
- In production (`VERCEL === '1'`, or `NODE_ENV === 'production'` when
  `APP_ENV !== 'development'`), the route passes an empty fallback `''` (never
  `socket.remoteAddress`) and sets `requireProxyTrust: true`, so missing
  `clientIpHeader`, `proxySecret`, or extracted `clientIp` fails closed (`503`).
  Outside production it falls back to the socket remote address from h3.
- The route computes the client IP and passes it to `proxyToGateway`, which
  sets `x-shield-client-ip: <ip>` and, when configured, `x-shield-proxy-secret`.
- Client-supplied `x-shield-client-ip` and `x-shield-proxy-secret` are dropped
  like `X-Forwarded-*` (WEB-PROXY-010 still holds).

Production on Vercel: web sets `NUXT_CLIENT_IP_HEADER=x-vercel-forwarded-for`
and `NUXT_API_PROXY_SECRET`; the gateway sets
`TRUSTED_CLIENT_IP_HEADER=x-shield-client-ip` and the same
`TRUSTED_PROXY_SECRET`.

### Bot protection (Vercel BotID)

`checkBotId()` exists only in JavaScript, so verification happens in the Nuxt
same-origin proxy, never in FastAPI. No Python dependency is added. The web app
adds the `botid` npm package (approved by the user, 2026-11-23). Per Vercel's
get-started guide, no `withBotId` wrapper, no `botid/nuxt` module and no manual
`vercel.json` rewrites are used.

Protected routes, defined once as `BOTID_PROTECTED_ROUTES` in
`apps/web/shared/utils/` and used by both the client plugin and the proxy:

| Method | Path |
| --- | --- |
| `POST` | `/api/v1/auth/anonymous` |
| `POST` | `/api/v1/auth/register` |
| `POST` | `/api/v1/auth/login` |
| `POST` | `/api/v1/game/run` |
| `POST` | `/api/v1/game/train` |

Paths and methods must match exactly what the browser sends; a mismatch makes
BotID treat all traffic on that route as bots.

**Client.** A Nuxt client plugin (`app/plugins/botid.client.ts`) calls
`initBotId({ protect: BOTID_PROTECTED_ROUTES })` from `botid/client/core`.

**Proxy.** For a request whose method and path exactly match a protected
route, the server route calls `checkBotId()` (`botid/server`) before
forwarding:

| Verdict | Proxy |
| --- | --- |
| `isBot: true` | answers `403` `{"detail": "Request blocked."}`; the gateway is not called |
| `isBot: false` | forwards with `x-shield-botid: pass` and `x-shield-proxy-secret` |
| `checkBotId()` throws | answers `503` `{"detail": "Bot check unavailable. Try again."}`; not forwarded (fail closed) |

Unprotected routes are forwarded without calling `checkBotId()`. A
client-supplied `x-shield-botid` is always dropped, like `x-shield-client-ip`.
`proxyToGateway` stays pure: the server route passes it the verdict (or a
`checkBot` function), so tests use a fake. Locally `checkBotId()` reports
not-bot, so development keeps working.

**Gateway.** `BOTID_REQUIRED` is derived from the same flag as the rate
limiter: on exactly when `APP_ENV == "production"`, off in local development.
When on, the five routes above answer `403` `{"detail": "Request blocked."}`
unless the request carries a valid `x-shield-proxy-secret` (equal to
`TRUSTED_PROXY_SECRET`, constant-time compare) **and** `x-shield-botid: pass`.
The check runs before rate limiting and before the handler, so a refused
request costs no model, Supabase or email call. If `BOTID_REQUIRED` is on and
`TRUSTED_PROXY_SECRET` is unset, those routes always answer `403` (fail closed)
and the gateway logs an error at startup. Calling the gateway directly
therefore cannot skip BotID.

**Vercel only.** BotID protects only the Vercel production deployment. Local
development, including Docker Compose (`mise run up`), runs with
`APP_ENV=development` (the Compose default and `apps/api/.env.example`), so
the gateway requires no BotID header and applies no rate limits there, and
`checkBotId()` reports not-bot. A self-hosted production deployment off Vercel
is not supported by this spec.

Production setup (documented in `docs/reference/configuration.md` and
`docs/how-to/`): web and gateway share `NUXT_API_PROXY_SECRET` /
`TRUSTED_PROXY_SECRET`; the web app is deployed on Vercel with BotID available
for the project.

### Production configuration guard

Production is Vercel + Supabase + Upstash Redis. Rate limits (this spec),
trained models (spec 0045) and the leaderboard index (spec 0044) depend on
Redis.

With `APP_ENV=production`, `build_container` refuses to build: it logs one
error and raises `ConfigurationError` unless `REDIS_URL`,
`TRUSTED_CLIENT_IP_HEADER` and `TRUSTED_PROXY_SECRET` are all set and
non-blank.
The check runs before any client is created, so a misconfigured deployment
fails at cold start with a clear message. On the web server, the Nuxt proxy
route (`/api/v1/[...path]`) enables `requireProxyTrust` in production
(`VERCEL === '1'`, or `NODE_ENV === 'production'` when
`APP_ENV !== 'development'`) and fails closed (`503`) with an error log when
`NUXT_CLIENT_IP_HEADER`, `NUXT_API_PROXY_SECRET`, or the extracted `clientIp`
is blank or missing (never falling back to the proxy's own socket address).
`APP_ENV=development` keeps the
in-memory fallbacks (limiter, model store, leaderboard store path) and does not
require proxy headers.

Supabase (`SUPABASE_URL`, `SUPABASE_KEY`) is required in **every** environment;
that check lives in spec 0046 (API-SUPA-001), and both checks report together
in one error when both fail. `mise run contract` and the API-DOCS tests are
unaffected because `create_app(...).openapi()` and a `TestClient` used without
its context manager do not run the lifespan that builds the container. Docs
(`docs/reference/configuration.md`) are updated during implementation.

## Acceptance criteria

Unless a criterion says otherwise, tests build `Settings(APP_ENV="production")`
with the in-memory limiter and a fake clock.

- **API-RATE-001**: Given one client IP, when it sends 30 requests spread across `/auth/login`, `/auth/register`, `/auth/recover` and `/auth/resend-confirmation` within 5 minutes and then a 31st to any of them, then calls 1–30 reach their handlers and call 31 answers `429` with an integer `Retry-After` ≥ 1 and the documented `detail`.
- **API-RATE-002**: Given one client IP, when `POST /auth/anonymous` is called 31 times within an hour, then call 31 answers `429` and sets no session cookie.
- **API-RATE-003**: Given one account email and requests from different IPs, when 10 logins with a wrong password fail within 15 minutes, then the 11th login answers `429` with `Retry-After` even with the correct password, and the identity fake records no verify call for it.
- **API-RATE-004**: Given 9 failed logins and then 5 successful logins for one email within 15 minutes, then none answers `429` (successes do not count toward the failed-login bucket).
- **API-RATE-005**: Given the failed-login bucket for an email is full, when the fake clock passes the 15-minute window, then a login with the correct password answers `200` (no permanent lockout).
- **API-RATE-006**: Given one email, when `POST /auth/recover` is called twice within 60 seconds, then the second answers `429`; given an unregistered email, the same two calls give the same status codes and bodies; after 60 seconds a third call is allowed.
- **API-RATE-007**: Given one email, when `POST /auth/resend-confirmation` is called twice within 60 seconds, then the second answers `429` and the identity fake records exactly one resend.
- **API-RATE-008**: Given one anonymous session, when `POST /game/run` (a level with an agent) is called 11 times within one minute, then call 11 answers `429` with `Retry-After` and the fake agent records at most 10 calls.
- **API-RATE-009**: Given one client IP and different sessions, when `POST /game/run` is called 31 times within a minute, then call 31 answers `429`; a different IP at the same time is limited only by its own counters.
- **API-RATE-010**: Given one signed-in account, when `POST /game/train` is called 11 times within a minute, then call 11 answers `429` and no training runs for it.
- **API-RATE-011**: Given `APP_ENV="development"`, when any limited route is called past its production limit, then no `429` is returned.
- **API-RATE-012**: Given a Redis-backed limiter (fake async Redis), when two `Container`s share the fake and together send 31 `POST /auth/register` calls from the same IP within 5 minutes, then the 31st call overall answers `429`.
- **API-RATE-013**: Given a Redis-backed limiter whose client raises on `INCR`, when a limited route is called past its limit, then the request is still limited by the in-memory counter and a warning is logged.
- **API-RATE-014**: Given limited requests from IP `203.0.113.7` and email `ada@example.com`, then no Redis key, in-memory key or log record contains either raw string.
- **API-IP-001**: Given `TRUSTED_CLIENT_IP_HEADER` unset, when a request carries `x-forwarded-for: 198.51.100.1`, then `client_address()` returns the socket peer.
- **API-IP-002**: Given `TRUSTED_CLIENT_IP_HEADER=x-shield-client-ip` and no `TRUSTED_PROXY_SECRET`, when a request carries `x-shield-client-ip: 198.51.100.1, 10.0.0.1`, then `client_address()` returns `198.51.100.1`.
- **API-IP-003**: Given `TRUSTED_CLIENT_IP_HEADER=x-shield-client-ip` and `TRUSTED_PROXY_SECRET=s3cret`, when a request carries the IP header but a missing or wrong `x-shield-proxy-secret`, then `client_address()` returns the socket peer; with the right secret it returns the header IP.
- **API-IP-004**: Given a trusted header whose value is not an IP address (`evil`, empty), then `client_address()` returns the socket peer.
- **API-IP-005**: Given a trusted header configured, when two clients with different header IPs each fail `POST /clearance` 5 times, then each is locked out independently (the admin `AttemptLimiter` uses the same `client_address()`).
- **WEB-RATE-001**: Given `proxyToGateway` called with `clientIp: '203.0.113.7'` and secret `s3cret`, when a request is proxied, then the fake `fetch` receives `x-shield-client-ip: 203.0.113.7` and `x-shield-proxy-secret: s3cret`.
- **WEB-RATE-002**: Given an incoming request with client-supplied `x-shield-client-ip` and `x-shield-proxy-secret`, when it is proxied with no `clientIp` and no secret, then neither header reaches the fake `fetch`.
- **WEB-RATE-003**: Given `clientIpFromHeaders(headers, 'x-vercel-forwarded-for', fallback)` with `x-vercel-forwarded-for: 203.0.113.7, 10.0.0.1`, then it returns `203.0.113.7`; with no header name configured or the header absent, it returns `fallback`.
- **WEB-RATE-004**: Given the web client receives a `429` from `/game/run` or an auth route, then the toast shows the gateway's `detail` (pure formatter in `app/utils/`, tested).
- **WEB-RATE-005**: Given `proxyToGateway` is called with `requireProxyTrust: true` (production Nuxt server route) when `clientIpHeader` (`NUXT_CLIENT_IP_HEADER`), `proxySecret` (`NUXT_API_PROXY_SECRET`), or `clientIp` is unset or blank, then it logs an error, makes zero upstream `fetch` calls, and returns `503` `{"detail": "Gateway unavailable."}`.
- **WEB-RATE-006**: Given `apps/web/nuxt.config.ts`, `apps/web/.env.example`, and `apps/web/server/routes/api/v1/[...path].ts`, then `runtimeConfig.clientIpHeader` defaults to `'x-vercel-forwarded-for'`, `.env.example` sets `NUXT_CLIENT_IP_HEADER=x-vercel-forwarded-for`, and `[...path].ts` passes `''` instead of `socket.remoteAddress` when `requireProxyTrust` is active.

- **WEB-BOTID-001**: Given `BOTID_PROTECTED_ROUTES`, then it equals exactly the five `{ path, method: 'POST' }` pairs in the table (paths under `/api/v1`, no trailing slash), and the client plugin passes that constant to `initBotId({ protect })` (fake `initBotId` records the argument).
- **WEB-BOTID-002**: Given a protected request (`POST /api/v1/game/run`) and a fake check returning `{ isBot: true }`, when it is proxied, then the answer is `403` with `{"detail": "Request blocked."}` and the fake `fetch` is never called.
- **WEB-BOTID-003**: Given a protected request and a fake check returning `{ isBot: false }`, when it is proxied with secret `s3cret`, then the fake `fetch` receives `x-shield-botid: pass` and `x-shield-proxy-secret: s3cret`.
- **WEB-BOTID-004**: Given an unprotected request (`GET /api/v1/game/levels`, or `GET /api/v1/game/run`), when it is proxied, then the bot check is never called and the fake `fetch` receives no `x-shield-botid`.
- **WEB-BOTID-005**: Given a request carrying a client-supplied `x-shield-botid: pass`, when it is proxied (protected or not, any verdict), then the forwarded headers contain `x-shield-botid` only if the proxy itself set it after an `isBot: false` verdict.
- **WEB-BOTID-006**: Given a protected request and a bot check that throws, when it is proxied, then the answer is `503` and the fake `fetch` is never called.
- **API-BOTID-001**: Given `APP_ENV="production"` and `TRUSTED_PROXY_SECRET="s3cret"`, when each of the five protected routes is called without `x-shield-botid: pass`, or with it but a missing or wrong `x-shield-proxy-secret`, then each answers `403` `{"detail": "Request blocked."}` and the handler's fakes (identity, agent, players store) record no call.
- **API-BOTID-002**: Given `APP_ENV="production"`, `TRUSTED_PROXY_SECRET="s3cret"`, and requests carrying `x-shield-proxy-secret: s3cret` and `x-shield-botid: pass`, when the protected routes are called, then they reach their handlers as before.
- **API-BOTID-003**: Given `APP_ENV="development"`, when the protected routes are called with no BotID or secret headers, then they reach their handlers.
- **API-BOTID-004**: Given `APP_ENV="production"` and `TRUSTED_PROXY_SECRET` unset, when a protected route is called with `x-shield-botid: pass`, then it answers `403`, and creating the app logs an error naming the missing secret.
- **API-BOTID-005**: Given `APP_ENV="production"`, when an unprotected route (`GET /game/levels`, `GET /auth/session`, `POST /auth/logout`) is called with no BotID headers, then it is not refused by the BotID check.
- **API-BOTID-006**: Given `APP_ENV="production"` and a request refused by the BotID check, then it does not increment any rate-limit counter (the BotID check runs first).

- **API-PROD-002**: Given `APP_ENV="production"`, Supabase set and `REDIS_URL` unset, when `build_container` runs, then it raises `ConfigurationError` naming `REDIS_URL`.
- **API-PROD-006**: Given `APP_ENV="production"` and `SUPABASE_URL`, `SUPABASE_KEY`, `REDIS_URL`, `TRUSTED_CLIENT_IP_HEADER` and `TRUSTED_PROXY_SECRET` all blank or unset, then one `ConfigurationError` message names all five (Supabase part from API-SUPA-001).
- **API-PROD-007**: Given `APP_ENV="development"`, Supabase set (fake client factory) and no `REDIS_URL`, when `build_container` runs, then it succeeds with the in-memory limiter and model store.
- **API-PROD-005**: Given `APP_ENV="production"` and `SUPABASE_URL`, `SUPABASE_KEY`, `REDIS_URL`, `TRUSTED_CLIENT_IP_HEADER` and `TRUSTED_PROXY_SECRET` all set (fake Supabase and Redis factories, no network), when `build_container` runs, then it succeeds and uses the Supabase stores and Redis.
- **API-PROD-008**: Given `APP_ENV="production"` with `SUPABASE_URL`, `SUPABASE_KEY` and `REDIS_URL` set, when either `TRUSTED_CLIENT_IP_HEADER` or `TRUSTED_PROXY_SECRET` is unset or whitespace-only, then `build_container` raises `ConfigurationError` naming the missing variable(s); in `APP_ENV="development"`, leaving both unset still succeeds.

## Security & privacy considerations

- Forwarded headers are client-controlled; they are trusted only when an
  operator names one, and, when a proxy secret is set, only from the proxy.
  Without the secret, a gateway reachable directly can be spoofed: the docs
  say to set the secret whenever the gateway has a public URL.
- `NUXT_API_PROXY_SECRET` is server-only runtime config, never `public`.
- BotID fails closed at both layers: a throwing check is `503` in the proxy,
  and the gateway refuses protected routes without the proxy's vouching headers.
  The `x-shield-botid` header means nothing without the proxy secret.
- Per-email limits on recover/resend give identical answers for known and
  unknown addresses.
- Redis failure falls back to local limits rather than disabling limiting.
- Docs: `docs/reference/configuration.md`, `apps/api/.env.example`,
  `apps/web/.env.example`, `docs/reference/http-api.md` (429s).

## Evaluation impact

None.

## Test impact

`APP_ENV` defaults to `production`, so without a change every existing API
test that posts to a protected route would get the BotID `403`. Setup edit: the
shared test harness builds `Settings(APP_ENV="development")` unless a test asks
for production (the API-RATE-*, API-BOTID-* and API-IP-* tests set
`APP_ENV="production"` explicitly). `test_api_docs.py` keeps its explicit
`APP_ENV` values. No assertion about existing behaviour is weakened.

### Retired IDs (never implemented)

- API-PROD-001 (Supabase required in production): moved to spec 0046 API-SUPA-001, which requires Supabase in every environment (SQLite removed by 0046).
- API-PROD-003 (blank settings named together): replaced by API-PROD-006 (same check, cross-referencing API-SUPA-001).
- API-PROD-004 (development succeeds with SQLite): SQLite removed by 0046; replaced by API-PROD-007.

## Open questions

None.

Resolved 2026-11-23: the shared-secret proxy design; limits on only in
production (`APP_ENV`), as fixed constants from the Sources above; Vercel BotID
(not Turnstile) for anonymous abuse, replacing a per-IP daily run cap;
BotID is Vercel-only (production runs on Vercel; local Docker runs with
`APP_ENV=development`, so BotID and rate limits are off there).

## Verification

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-RATE-001, API-RATE-002, API-RATE-003, API-RATE-004, API-RATE-005, API-RATE-006, API-RATE-007, API-RATE-008, API-RATE-009, API-RATE-010, API-RATE-011, API-RATE-012, API-RATE-013, API-RATE-014, API-IP-001, API-IP-002, API-IP-003, API-IP-004, API-IP-005, WEB-RATE-001, WEB-RATE-002, WEB-RATE-003, WEB-RATE-004, WEB-BOTID-001, WEB-BOTID-002, WEB-BOTID-003, WEB-BOTID-004, WEB-BOTID-005, WEB-BOTID-006, API-BOTID-001, API-BOTID-002, API-BOTID-003, API-BOTID-004, API-BOTID-005, API-BOTID-006, API-PROD-002, API-PROD-006, API-PROD-007, API-PROD-005
- Red: 39 failing test(s) before implementation (`apps/api/tests/test_rate_limit_and_botid.py`, `apps/api/tests/test_rate_limit_and_botid.py`, `apps/api/tests/test_rate_limit_and_botid.py`)
- Green: 54 passing test(s)
- Gate: `mise run check` passed

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-PROD-006, API-PROD-008, WEB-RATE-005
- Red: 3 failing test(s) before implementation (`apps/api/tests/test_rate_limit_and_botid.py::test_production_build_container_requires_redis_and_supabase_together`, `apps/api/tests/test_rate_limit_and_botid.py::test_production_build_container_requires_trusted_ip_header_and_proxy_secret`, `rate limiting, client IP and BotID (spec 0043) [WEB-RATE-005] fails closed with 503 when production proxy lacks clientIpHeader or proxySecret`)
- Green: 3 passing test(s)
- Gate: `mise run check` passed

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: WEB-RATE-005, WEB-RATE-006
- Red: 2 failing test(s) before implementation (`rate limiting, client IP and BotID (spec 0043) [WEB-RATE-005] fails closed with 503 when production proxy lacks clientIpHeader, proxySecret, or clientIp`, `rate limiting, client IP and BotID (spec 0043) [WEB-RATE-006] defaults clientIpHeader to x-vercel-forwarded-for and avoids socket IP fallback in production`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
