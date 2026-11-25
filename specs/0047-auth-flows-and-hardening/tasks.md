# 0047 — Auth flows and hardening: tasks

Run as one SDD cycle (or split into 2–3 slices: confirmation, recovery/email-change, hardening). `mise run sdd:done` ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0047 [IDs…]`
- [x] **API-AUTH-001**: write failing test (register mints `HttpOnly` `shield_auth_browser` cookie and stores browser-bound flow + PKCE verifier)
- [x] **API-AUTH-002**: write failing test (same-browser confirm auto-verifies, clears browser cookie, and signs in)
- [x] **API-AUTH-003**: write failing test (different/missing browser cookie returns `confirmation_required` without verifying)
- [x] **API-AUTH-004**: write failing test (manual `confirm: true` verifies without signing in)
- [x] **API-AUTH-005**: write failing test (invalid/expired token returns `400`, outage returns `503`)
- [x] **API-AUTH-006**: write failing test (recover passes `/auth/reset-password?flow=`, stores 30m flow, and sets `HttpOnly` browser cookie)
- [x] **API-AUTH-007**: write failing test (`POST /auth/reset-password` updates password and revokes all sessions without auto-login)
- [x] **API-AUTH-008**: write failing test (email change passes `email_redirect_to`, sets browser cookie, and enforces rate limit)
- [x] **API-AUTH-009**: write failing test (unconfirmed login does not increment `login_fail`)
- [x] **API-AUTH-010**: write failing test (Redis-backed attempt limiting across containers for clearance and account)
- [x] **API-AUTH-011**: write failing test (register returns `503` on outage, `202` on existing email)
- [x] **API-AUTH-012**: write failing test (BotID required on recover, resend, confirm, reset-password)
- [x] **API-AUTH-013**: write failing test (`SupabasePlayerStore._insert_session` prunes expired sessions)
- [x] **API-AUTH-014**: write failing test (production `build_container` rejects blank/localhost `WEB_BASE_URL`)
- [x] **API-AUTH-015**: write failing test (`Cache-Control: no-store` on auth/clearance responses + OpenAPI contract includes confirm & reset-password routes)
- [x] **WEB-AUTH-001**: write failing test (`/auth/confirmed` strips URL params and auto-signs in on `signed_in`)
- [x] **WEB-AUTH-002**: write failing test (`/auth/confirmed` shows manual confirmation button on `confirmation_required`)
- [x] **WEB-AUTH-003**: write failing test (`/auth/confirmed` shows error state on error/missing params)
- [x] **WEB-AUTH-004**: write failing test (`nuxt.config.ts` sets `Referrer-Policy: no-referrer` and `Cache-Control: no-store` on `/auth/**`)
- [x] **WEB-AUTH-005**: write failing test (`/auth/reset-password` strips params and submits new password)
- [x] **WEB-AUTH-006**: write failing test (`/auth/recover` client schema validation + `/settings` dual-inbox toast)
- [x] **WEB-AUTH-007**: write failing test (login/register send untrimmed passwords)
- [x] **WEB-AUTH-008**: write failing test (`loginFailure` distinguishes BotID `403` from unconfirmed `403`)
- [x] **WEB-AUTH-009**: write failing test (`botid.client.ts` uses `enforce: 'pre'` and `loadAccess` lives in `dashboard.vue`)
- [x] **WEB-AUTH-010**: write failing test (`proxyToGateway` blocks cross-site state-changing requests via `Sec-Fetch-Site` / `Origin`)
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Regenerate the API contract (`mise run contract`)
- [ ] Update `docs/reference/configuration.md`, `docs/reference/http-api.md`, `apps/api/.env.example`, and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
