# 0041 — Same-origin API proxy

- **Status:** Implemented
- **Area:** WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-21
- **Related:** [ADR 0004: frontend talks only to the gateway](../../docs/explanation/decisions/0004-frontend-talks-only-to-gateway.md), [0012-clearance-sessions](../0012-clearance-sessions/spec.md), [0025-account-settings](../0025-account-settings/spec.md), [0028-instant-leaderboard](../0028-instant-leaderboard/spec.md). Supersedes the `apiBaseUrl`-based URLs described in 0012, 0025 and 0028; their cookie and stream behaviour is unchanged.

## Problem

The browser calls the gateway directly at `runtimeConfig.public.apiBaseUrl`
(`apps/web/app/composables/useShieldApi.ts:37`, `useLeaderboard.ts:147`) with
`credentials: 'include'`. Sessions are HttpOnly cookies set by the gateway with
`SameSite=Lax` (`routers/auth.py:51`, `routers/clearance.py:59`, `routers/account.py:201`).

Deployed on Vercel without a custom domain, the web app and the gateway live on
two `*.vercel.app` hosts. `vercel.app` is on the Public Suffix List, so the two
hosts are **different sites**: the browser treats the gateway's cookies as
third-party, does not send `SameSite=Lax` cookies on the web app's `fetch`
calls, and Safari/Chrome increasingly block them outright. Players and admins
cannot stay signed in.

## Goals

- The browser only ever talks to the web app's own origin; session cookies are
  first-party on every deployment (two `vercel.app` hosts, Docker Compose, local dev).
- The web server forwards `/api/v1/**` to the gateway unchanged (method, query,
  body, cookies, status, `Set-Cookie`, streamed bodies including SSE).
- The gateway's address becomes server-side configuration, not a public setting.

## Non-goals

- No gateway (`apps/api`) changes and no HTTP contract changes.
- Per-client rate limiting behind the proxy. The clearance attempt limiter keys on
  the socket peer (`dependencies.py:client_address`); behind the proxy every request
  comes from the web server, so failed admin sign-ins share one bucket. This is a
  known limitation recorded under Security and left for a follow-up spec.
- Custom domains, CDN caching of API responses, or `SameSite=None` cookies.

## Behaviour

| Item | Before | After |
| --- | --- | --- |
| REST base URL used by the browser | `<apiBaseUrl>/api/v1` (absolute, other origin) | `/api/v1` (same origin) |
| Leaderboard stream URL | `<apiBaseUrl>/api/v1/game/scores/stream` | `/api/v1/game/scores/stream` |
| Gateway address setting | `NUXT_PUBLIC_API_BASE_URL` (public, shipped to the browser) | `NUXT_API_PROXY_TARGET` (private, server only), default `http://localhost:8000` |
| Who receives `Set-Cookie` | the gateway's host | the web app's host |

Proxy rules, for a request to the web server at path `P` with query `Q`:

| Condition | Result |
| --- | --- |
| `P` starts with `/api/v1/`, has no empty segment, no backslash and no dot-segment (raw or percent-encoded, including `%2f` inside a segment) | forwarded to `<target>P?Q`; response status, body and headers returned except the stripped response headers below |
| any other `P` (escapes, `//`, `\`, `%2f`, `/api/v1`, `/api/v1evil`) | `404` `{"detail": "Not found."}`, gateway not called |
| `NUXT_API_PROXY_TARGET` missing, malformed or not `http(s)` | `502` `{"detail": "Gateway unavailable."}`, gateway not called |
| gateway unreachable / network error | `502` `{"detail": "Gateway unavailable."}` (`application/json`), no target in the body |
| gateway answers any status (2xx, 3xx, 4xx, 5xx) | the same status is returned; redirects are not followed server-side |

Request: method and query preserved. `GET`/`HEAD` are sent with no body; other
methods send the request body buffered (Vercel already caps request bodies, and
API bodies are small JSON). Header names match case-insensitively. Dropped request
headers: `host`, `content-length` (recomputed by `fetch`), hop-by-hop (`connection`,
`keep-alive`, `transfer-encoding`, `upgrade`, `te`, `trailer`, `proxy-*`) and
client-supplied `forwarded` / `x-forwarded-*`. Everything else (including
`cookie`, `content-type`, `accept`, `authorization`, `last-event-id`) is forwarded.

Response: dropped headers are hop-by-hop ones plus `content-encoding` and
`content-length`, because `fetch` has already decoded the body. Every `Set-Cookie`
is kept as a separate value. The body is passed through as a stream.

Out of scope: no proxy-level timeout (the platform's function limit applies) and
no special handling for client disconnects beyond what the runtime does.

## Acceptance criteria

Criteria 003–015 are observed on the pure `proxyToGateway(request, target, fetchImpl)`
with a fake `fetch` as the observation point (no network).

- **WEB-PROXY-001**: Given `SHIELD_API_PREFIX`, then it equals `/api/v1`, and no source file under `apps/web/app` reads `public.apiBaseUrl`.
- **WEB-PROXY-002**: Given `useLeaderboard`, then it reads leaderboard data only through `useShieldApi()` (under `SHIELD_API_PREFIX`), and it references no stream path and no hard-coded gateway URL.
- **WEB-PROXY-003**: Given target `https://gw.example` (with or without a trailing slash) and a request to `/api/v1/game/levels?difficulty=Easy`, when it is proxied, then the fake `fetch` is called with `https://gw.example/api/v1/game/levels?difficulty=Easy`.
- **WEB-PROXY-004**: Given a dot-segment path (`/api/v1/../admin`, `/api/v1/%2e%2e/admin`, `/api/v1/%2E%2E/admin`, `/api/v1/.%2e/admin`), when it is proxied, then the answer is `404` and the fake `fetch` is never called.
- **WEB-PROXY-005**: Given a path with an empty segment, backslash or encoded slash (`/api/v1//evil.example/x`, `/api/v1/..\admin`, `/api/v1/a%2fb`, `/api/v1/a%5cb`), when it is proxied, then the answer is `404` and the fake `fetch` is never called.
- **WEB-PROXY-006**: Given a path outside the prefix (`/api/v1`, `/api/v1evil`, `/api/v2/x`), when it is proxied, then the answer is `404` and the fake `fetch` is never called.
- **WEB-PROXY-007**: Given a `POST` with a JSON body, `Cookie`, `Content-Type` and `Authorization`, when it is proxied, then the fake `fetch` receives the same method, the same body bytes and those three headers.
- **WEB-PROXY-008**: Given a `GET` and a `HEAD` request, when they are proxied, then the fake `fetch` receives no body.
- **WEB-PROXY-009**: Given a request with `Host`, `Connection`, `Keep-Alive`, `Transfer-Encoding`, `Upgrade`, `TE`, `Trailer`, `Proxy-Authorization` and `Content-Length` (in mixed case), when it is proxied, then none of them reach the fake `fetch`.
- **WEB-PROXY-010**: Given a request with client-supplied `Forwarded`, `X-Forwarded-For` and `X-Forwarded-Host`, when it is proxied, then none of them reach the fake `fetch`.
- **WEB-PROXY-011**: Given the gateway answers `201`, `401` or `500` with two `Set-Cookie` headers and a body, when the proxy returns, then the response has the same status, `headers.getSetCookie()` returns both values unchanged, and the body is the same.
- **WEB-PROXY-012**: Given the gateway answers with `Content-Encoding: gzip`, `Content-Length` and `Connection` headers, when the proxy returns, then the response carries none of those three headers.
- **WEB-PROXY-013**: Given the gateway answers `text/event-stream` with `Cache-Control: no-cache` and a body stream that has sent one chunk but not closed, when the proxy returns, then that first chunk can be read from the response body before the upstream closes, and `Content-Type` and `Cache-Control` are preserved.
- **WEB-PROXY-014**: Given the gateway answers `302` with a `Location`, when it is proxied, then the fake `fetch` was called with `redirect: 'manual'` and the response is the `302` with the same `Location`.
- **WEB-PROXY-015**: Given the fake `fetch` rejects (network error), or the target is empty, not a URL, or not `http(s)` (e.g. `file:///etc`), when a request is proxied, then the answer is `502` with `Content-Type: application/json`, body `{"detail": "Gateway unavailable."}`, and the body does not contain the target.

## Security & privacy considerations

- **Mitigated:** session cookies become first-party; no `SameSite=None` and no
  cross-origin credentialed requests. CORS on the gateway is no longer exercised
  by the browser.
- **SSRF / path escape:** the proxy only reaches the configured target under
  `/api/v1/`; dot-segments, empty segments, backslashes and encoded slashes are
  rejected (WEB-PROXY-004–006), and redirects are never followed server-side
  (WEB-PROXY-014). A bad target fails closed (WEB-PROXY-015).
- **Header spoofing:** client-supplied `Forwarded`/`X-Forwarded-*` are dropped so a
  later gateway change that trusts them cannot be fooled (WEB-PROXY-010).
- **No leakage:** errors are generic and never echo the target (WEB-PROXY-015).
  The target is private runtime config, so it is not in the client bundle.
- **Known limitation (not fixed here):** the gateway's clearance attempt limiter
  sees the web server as the only client, so five failed admin sign-ins from anyone
  lock out admin sign-in for everyone for `CLEARANCE_WINDOW_MINUTES`. Player
  account re-authentication is keyed by email and is unaffected. On Vercel the
  limiter is also per-instance memory. A follow-up spec should forward the client
  IP with a shared proxy secret the gateway verifies.
- **Follow-ups found in review (not vulnerabilities today, because the gateway
  trusts only the socket peer and emits no absolute redirects):** other client-IP
  headers (`x-real-ip`, `x-vercel-forwarded-for`, `cf-connecting-ip`, `true-client-ip`)
  are still forwarded and must be dropped before the gateway trusts any client IP,
  and an absolute `Location` pointing at the gateway would not be rewritten.
- **Client disconnects:** the Nitro route aborts the upstream request when the
  browser connection closes, so closed tabs do not hold gateway streams open.
- **SSE on Vercel:** a streamed response ends at the function's max duration;
  `EventSource` reconnects automatically, so the leaderboard keeps updating.

## Evaluation impact

None: no engine, scoring or classifier change.

## Open questions

None.

## Verification

### 2026-11-21 · commit d31b9c5 (+ uncommitted changes)

- Criteria: WEB-PROXY-001, WEB-PROXY-002, WEB-PROXY-003, WEB-PROXY-004, WEB-PROXY-005, WEB-PROXY-006, WEB-PROXY-007, WEB-PROXY-008, WEB-PROXY-009, WEB-PROXY-010, WEB-PROXY-011, WEB-PROXY-012, WEB-PROXY-013, WEB-PROXY-014, WEB-PROXY-015
- Red: 15 failing test(s) before implementation (`/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/apiProxy.test.ts`, `/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/apiProxy.test.ts`, `/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/apiProxy.test.ts`)
- Green: 15 passing test(s)
- Gate: `mise run check` passed
