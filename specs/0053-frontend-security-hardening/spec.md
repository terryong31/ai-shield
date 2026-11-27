# 0053 — Frontend security hardening

- **Status:** Implemented
- **Area:** WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-26
- **Related:** [0012-clearance-sessions](../0012-clearance-sessions/spec.md), [0041-same-origin-api-proxy](../0041-same-origin-api-proxy/spec.md), [0043-rate-limiting-and-client-ip](../0043-rate-limiting-and-client-ip/spec.md), [0045-train-upload-hardening](../0045-train-upload-hardening/spec.md), [0047-auth-flows-and-hardening](../0047-auth-flows-and-hardening/spec.md), [0049-stripe-pass-checkout](../0049-stripe-pass-checkout/spec.md)

## Problem

A security audit of `apps/web` found gaps in browser defence-in-depth, proxy protection, URL handling, and admin UX:

1. **Missing global HTTP security headers.** Only `/auth/**` sets `Referrer-Policy` and `Cache-Control`. All other routes lack `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Permissions-Policy`, `Referrer-Policy`, `Cross-Origin-Opener-Policy`, and production `Strict-Transport-Security`. Authenticated pages (`/_console/**`, `/settings`, `/plans`) also lack `Cache-Control: no-store`.
2. **URL parameter content spoofing on auth pages.** `/auth/confirmed` and `/auth/reset-password` render `route.query.error_description` directly in the UI. An attacker can craft a link that shows arbitrary phishing text inside the official interface.
3. **Auth query tokens can leak to client analytics.** `@vercel/analytics` runs globally on every route. `/auth/confirmed` and `/auth/reset-password` strip `code` and `token_hash` in `onMounted`, which runs after initial page load.
4. **Unbounded request body buffering in the Nitro proxy.** `proxyToGateway` calls `request.arrayBuffer()` without a byte limit. Large POST payloads can exhaust web server memory in non-Vercel deployments.
5. **Permissive CSRF origin check in the Nitro proxy.** `proxyToGateway` rejects `sec-fetch-site: cross-site` and mismatched `Origin`, but allows `sec-fetch-site: same-site` and allows production state-changing requests that omit both `Origin` and `Sec-Fetch-Site`.
6. **Unconfirmed destructive admin action and unauthenticated prefetch.** Clicking **Clear scoreboard** in `/_console` deletes all scores immediately with no confirmation dialog. `/_console` also calls `GET /api/v1/game/scores` on mount before admin clearance is granted.
7. **Additional hardening gaps.** `/plans` redirects externally to the checkout URL without checking the scheme and host; `app.vue` injects `JSON.stringify(...)` into a JSON-LD `<script>` tag without escaping `<`; `public/robots.txt` discloses `/_console`; the Change Email modal in `/settings` omits a Zod schema; and `apps/web/package.json` uses floating `"latest"` tags in `devDependencies`.

## Goals

- Enforce baseline HTTP security headers across all `apps/web` routes in both Vercel and Docker/Node deployments, and disable caching on authenticated pages.
- Eliminate URL-driven text spoofing and prevent auth query tokens from reaching client analytics.
- Harden the `/api/v1` Nitro proxy with a request body size cap and strict same-origin CSRF checks.
- Protect destructive admin actions with explicit confirmation and gate admin data fetches on clearance.
- Close remaining frontend defence-in-depth and supply-chain hygiene gaps.

## Non-goals

- Changes to `packages/engine`, `apps/api`, Supabase migrations, or the OpenAPI contract.
- Adding a new third-party security framework or WAF rule set.
- Replacing Vercel BotID or changing session cookie lifetimes.
- Pinning base Docker image SHA256 digests (tracked separately in deployment ops).

## Behaviour

### 1. Global HTTP security headers and route caching

`apps/web/nuxt.config.ts` sets baseline security headers on `/**` through `routeRules`:

| Header | Value | Scope |
| --- | --- | --- |
| `Content-Security-Policy` | Policy with `default-src 'self'`, `base-uri 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, and explicit allowances for Nuxt, Vue Flow styles, BotID, and Vercel Analytics/Speed Insights | `/**` |
| `X-Frame-Options` | `DENY` | `/**` |
| `X-Content-Type-Options` | `nosniff` | `/**` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` (overridden to `no-referrer` on `/auth/**`) | `/**` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=()` | `/**` |
| `Cross-Origin-Opener-Policy` | `same-origin` | `/**` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | `/**` in production only (`NODE_ENV === 'production'`) |
| `Cache-Control` | `no-store` | `/auth/**`, `/_console`, `/_console/**`, `/settings`, `/plans` |

### 2. Auth URL error allowlist and analytics scrubbing

- `/auth/confirmed` and `/auth/reset-password` never display raw `route.query.error_description`.
- A pure helper maps known `error_code` values (for example `otp_expired`, `access_denied`) to static messages and falls back to a fixed generic message for all unknown or missing codes.
- Client analytics must not record query parameters from `/auth/**` routes (either by dropping `/auth/**` events or stripping the query string in `beforeSend`).

### 3. Nitro `/api/v1` proxy hardening

- **Body size limit:** `proxyToGateway` enforces a maximum request body size (`2 * 1024 * 1024` bytes by default, above the 1.25 MB custom ML training CSV limit). If `Content-Length` exceeds the limit or the streamed body exceeds the limit, the proxy returns `413 {"detail": "Request body too large."}` and does not call the gateway.
- **Strict same-origin CSRF check:** For `POST`, `PUT`, `PATCH`, and `DELETE`:
  - Reject with `403 {"detail": "Cross-site request blocked."}` if `Sec-Fetch-Site` is present and is neither `same-origin` nor `none` (this blocks `cross-site` and `same-site`).
  - Reject with `403` if `Origin` is present and does not match the request origin.
  - When `requireProxyTrust` is `true` (production), reject with `403` if both `Origin` and `Sec-Fetch-Site` are absent.

### 4. Admin console hardening

- `/_console` does not request `GET /api/v1/game/scores` while `access.allowed` is `false`. It loads scores only after admin clearance is granted.
- Clicking **Clear scoreboard** opens a confirmation modal. The admin must type `CLEAR` before the confirm button enables and sends `DELETE /api/v1/game/scores`.

### 5. Defence-in-depth and supply-chain hygiene

- **Checkout redirect validation:** Before navigating externally in `/plans`, a pure helper checks that the URL uses `https:` and host `checkout.stripe.com`. Invalid URLs are blocked and show the existing checkout error toast.
- **JSON-LD escaping:** `app.vue` serializes JSON-LD through a pure helper that escapes `<` as `\u003c` so no value can break out of `<script type="application/ld+json">`.
- **`robots.txt`:** Remove `Disallow: /_console` from `apps/web/public/robots.txt`. The page remains `noindex, nofollow` via `useSeoMeta`.
- **Change-email form schema:** The Change Email modal in `/settings` validates `email` and `password` with a Zod schema before submit.
- **Pinned `devDependencies`:** Replace `"latest"` version specs in `apps/web/package.json` with explicit semver ranges matching the installed lockfile versions.

## Acceptance criteria

- **WEB-SEC-001**: Given the Nuxt security header configuration, then `/**` sets `Content-Security-Policy` (including `default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, and `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and `Cross-Origin-Opener-Policy: same-origin`; production builds also set `Strict-Transport-Security`; and `/auth/**` keeps `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.
- **WEB-SEC-002**: Given the Nuxt `routeRules` configuration, then `/_console`, `/_console/**`, `/settings`, and `/plans` each set `Cache-Control: no-store`.
- **WEB-SEC-003**: Given `/auth/confirmed` or `/auth/reset-password` receives an arbitrary `error_description` query parameter (for example `?error=1&error_description=Call+attacker`), then the page ignores `error_description` and shows only a static allowlisted message for `error_code` or the default invalid/expired message.
- **WEB-SEC-004**: Given a client analytics event for `/auth/confirmed?code=secret&flow=123` or `/auth/reset-password?token_hash=secret`, when the analytics `beforeSend` sanitizer runs, then the event is either dropped or its URL query string is removed before transmission.
- **WEB-SEC-005**: Given a `POST` request to `/api/v1/game/train` whose `Content-Length` or body exceeds the proxy byte limit (2 MiB), when `proxyToGateway` handles the request, then it returns `413 {"detail": "Request body too large."}` and does not invoke `fetchImpl`.
- **WEB-SEC-006**: Given a `POST`, `PUT`, `PATCH`, or `DELETE` request to `proxyToGateway`, when `Sec-Fetch-Site` is `same-site` or `cross-site`, or when `requireProxyTrust` is `true` and both `Origin` and `Sec-Fetch-Site` are absent, then `proxyToGateway` returns `403 {"detail": "Cross-site request blocked."}` and does not invoke `fetchImpl`.
- **WEB-SEC-007**: Given `/_console` with admin access granted and scores loaded, when the admin clicks **Clear scoreboard**, then a confirmation modal opens and `DELETE /api/v1/game/scores` is only enabled and called after the admin enters `CLEAR`.
- **WEB-SEC-008**: Given `/_console` mounts without admin clearance (`access.allowed === false`), then `GET /api/v1/game/scores` is not called until `access.allowed` becomes `true`.
- **WEB-SEC-009**: Given `POST /api/v1/billing/checkout` returns a URL that is not `https://checkout.stripe.com/...` (such as `javascript:alert(1)`, `http://checkout.stripe.com/...`, or `https://evil.example/...`), when `/plans` validates the redirect URL, then external navigation is blocked and an error toast is shown.
- **WEB-SEC-010**: Given a JSON-LD object containing `</script>` in a string field, when `serializeJsonLd` formats it for `app.vue`, then `<` is escaped as `\u003c` and the output remains valid JSON.
- **WEB-SEC-011**: Given `apps/web/public/robots.txt`, then it does not contain `/_console`.
- **WEB-SEC-012**: Given `apps/web/app/pages/settings.vue`, then the Change Email `UForm` binds a Zod schema validating email and current password; and given `apps/web/package.json`, then no dependency or devDependency uses `"latest"`.

## Changes to earlier criteria

| Earlier criterion | Spec | Changed by | Change |
| --- | --- | --- | --- |
| WEB-GAME-016, WEB-GAME-017 | 0016 | WEB-SEC-011 | `robots.txt` no longer disallows `/_console`; the page stays `noindex, nofollow` |
| WEB-AUTH-004 | 0047 | WEB-SEC-001 | The `/auth/**` headers live in `app/utils/securityHeaders.ts`, which `nuxt.config.ts` uses as its `routeRules` |

## Security & privacy considerations

- **Fail-closed defaults:** Proxy body limit, CSRF origin check, checkout URL validation, and auth error mapping all fail closed on unexpected or malformed input.
- **No secrets in client code:** All checks operate on public configuration, headers, or pure validation helpers. No backend credentials or tokens are added to the browser.
- **CSP compatibility:** Verify Vue Flow inline styles, Nuxt hydration scripts, BotID, and Vercel Analytics/Speed Insights in local dev and preview deployments so CSP does not break board rendering or bot checks.

## Evaluation impact

None. No engine scoring or classifier change.

## Open questions

None.

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: WEB-SEC-001, WEB-SEC-002, WEB-SEC-003, WEB-SEC-004, WEB-SEC-005, WEB-SEC-006, WEB-SEC-007, WEB-SEC-008, WEB-SEC-009, WEB-SEC-010, WEB-SEC-011, WEB-SEC-012
- Red: 12 failing test(s) before implementation (`/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/frontendSecurity.test.ts`, `/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/frontendSecurity.test.ts`, `/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/frontendSecurity.test.ts`)
- Green: 12 passing test(s)
- Gate: `mise run check` passed

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: WEB-SEC-001
- Red: 1 failing test(s) before implementation (`Frontend security hardening (spec 0053) [WEB-SEC-001] sets the baseline security headers on every route`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: WEB-SEC-006
- Red: 1 failing test(s) before implementation (`Frontend security hardening (spec 0053) [WEB-SEC-006] blocks same-site, cross-site and unlabelled state-changing requests`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
