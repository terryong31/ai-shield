# 0047 — Auth flows and hardening

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-25
- **Related:** [0012-clearance-sessions](../0012-clearance-sessions/spec.md), [0025-account-settings](../0025-account-settings/spec.md), [0027-player-email-confirmation](../0027-player-email-confirmation/spec.md), [0036-password-strength-validation](../0036-password-strength-validation/spec.md), [0042-run-spend-and-account-integrity](../0042-run-spend-and-account-integrity/spec.md), [0043-rate-limiting-and-client-ip](../0043-rate-limiting-and-client-ip/spec.md)

## Problem

An audit of the authentication system found broken user flows and security gaps across `apps/api` and `apps/web`:

1. **Email confirmation fails to show UI, leaks the PKCE code, and never signs the player in.** `WEB_BASE_URL` defaults to `http://localhost:3000` and is not checked in production, so Supabase falls back to the Site URL (`/?code=<uuid>`). Even when the link reaches `/auth/confirmed`, the server discards the PKCE `code_verifier` after `sign_up()`, the page ignores URL parameters and error states, `?code=...` stays in the address bar, and the player is not signed in.
2. **Email link scanners can consume confirmation links.** Corporate mail scanners (for example, Outlook Safe Links) pre-fetch URLs in confirmation emails. Without a browser-binding check and a human confirmation step for unrecognised browsers, a scanner can trigger confirmation unexpectedly.
3. **Password recovery is a dead end.** `reset_password_for_email()` passes no `redirect_to`, there is no `/auth/reset-password` page, and there is no API endpoint to set a new password from a recovery link.
4. **Email change confirmation has no redirect target and leaves a stale session.** `update_user({"email": new})` passes no `email_redirect_to`, the settings toast mentions only the new inbox when Supabase double-confirmation is active, and the active session keeps the old email until manual sign-out (which breaks re-authentication on settings actions).
5. **Password trimming mismatch locks players out.** `usePlayerAuth` trims passwords on login and register, while Settings and Admin login do not.
6. **BotID `403` collides with unconfirmed email `403`.** On `/auth/login`, any `403` shows "Confirm your email first", even when BotID blocked the request.
7. **Admin and account brute-force limits are in-memory only.** `AttemptLimiter` does not use Redis, so cold starts and parallel instances on Vercel reset the counter.
8. **Additional hardening gaps:** `/auth/register` masks 5xx/SMTP outages as `202` success; `/auth/recover` and `/auth/resend-confirmation` lack BotID protection; `POST /auth/account/email` allows unlimited authenticated email enumeration via `409`; `players.sessions` never prunes expired rows; `EmailNotConfirmedError` increments the `login_fail` rate limit; `/auth/recover` lacks client-side schema validation; `botid.client.ts` omits `enforce: 'pre'`; and `app.vue` calls `GET /clearance` on every public page load.

## Goals

- Bind email confirmation, password recovery, and email-change flows to the originating browser via a browser-side cookie validated by the gateway.
- Protect confirmation links from automated email scanners (such as Outlook Safe Links): unrecognised browsers see a manual confirmation screen, while the originating browser auto-confirms, signs the player in, clears sensitive URL parameters, and shows clear confirmation UI.
- Complete the password recovery and email-change flows end-to-end.
- Eliminate the password trimming bug, `403` status collision, in-memory-only brute-force limiter, silent registration outages, and remaining auth security and UX gaps.

## Non-goals

- OAuth, social login, passkeys, or magic-link sign-in.
- Sliding session TTL extension (sessions remain fixed at `SESSION_TTL_MINUTES`).
- Migrating unsaved anonymous boards into a newly registered account.
- Custom SMTP server hosting (remains a Supabase dashboard setting).

## Behaviour

### 1. Browser-binding cookie and auth flow store

The web client maintains a browser-side cookie `shield_auth_browser` (random URL-safe token, 32 to 128 characters matching `^[A-Za-z0-9_-]{32,128}$`, `Path=/`, `SameSite=Lax`, `Secure` on HTTPS). The client ensures this cookie exists before calling `/auth/register`, `/auth/resend-confirmation`, `/auth/recover`, or `/auth/account/email`, so the browser sends it in the `Cookie` header on same-origin `/api/v1/**` requests.

When the gateway handles one of those four routes:

1. It reads `shield_auth_browser` from the request cookies and validates its format. If the cookie is missing or invalid, the gateway proceeds without a browser binding (the user will get the manual confirmation screen instead of auto-sign-in).
2. It generates a random `flow_id` (URL-safe token), captures the PKCE `code_verifier` from the throwaway Supabase client (when PKCE is used), and stores a flow record in Redis (or in-memory in development) with a 1-hour TTL:
   `{ flow_id, purpose, browser_hash: sha256(cookie) | None, code_verifier: str | None }`.
   Raw cookie values are never stored or logged.
3. It passes `redirect_to` / `email_redirect_to` to Supabase with the `flow` query parameter:
   - Signup / resend confirmation: `<WEB_BASE_URL>/auth/confirmed?flow=<flow_id>`
   - Email change: `<WEB_BASE_URL>/auth/confirmed?flow=<flow_id>&intent=email_change`
   - Password recovery: `<WEB_BASE_URL>/auth/reset-password?flow=<flow_id>`

### 2. Email confirmation and Outlook scanner defence (`POST /api/v1/auth/confirm`)

The web page `/auth/confirmed` never confirms on HTTP `GET` (SSR). On client mount, it immediately removes `code`, `token_hash`, `type`, `flow`, `error`, `error_code`, and `error_description` from the browser URL via `router.replace` (keeping the values in memory only).

- If the URL contained `error` or `error_code` (for example, `otp_expired`), the page shows an expired/invalid link state with a button to resend the confirmation email (or return to sign in).
- If the URL contained neither `code` nor `token_hash`, the page shows a neutral invalid/missing link state with a **Sign in** button (never faking "Email confirmed").
- Otherwise, the page sends `POST /api/v1/auth/confirm` with `{ flow_id, code?, token_hash?, type?, confirm: false }`. The browser sends its `shield_auth_browser` cookie in the request header.

Gateway behaviour for `POST /api/v1/auth/confirm`:

| Condition | `confirm` flag | Gateway action | HTTP response |
| --- | --- | --- | --- |
| Flow exists, `browser_hash` matches `sha256(cookie)` (same browser) | `false` or `true` | Verify via Supabase (`verify_otp` for `token_hash`, or `exchange_code_for_session` for `code` + stored `code_verifier`), sign out Supabase session, delete flow record, run `_open_verified()`, set `shield_player_session` cookie | `200 {"status": "signed_in", "session": PlayerSessionStatus}` |
| Flow missing, or cookie missing, or `browser_hash` differs (different browser, device, or Outlook scanner) | `false` (auto check) | **Do not** call Supabase verify/exchange and **do not** consume the token or flow | `200 {"status": "confirmation_required"}` |
| Different browser / missing cookie, after human clicks the confirm button | `true` (manual confirm) | If `token_hash` is present, call `verify_otp` and sign out Supabase session. If only `code` is present (already verified by Supabase on redirect), complete without auto-sign-in. Delete flow record if present. Never set `shield_player_session`. | `200 {"status": "confirmed"}` |
| Invalid or expired token/code from Supabase | `false` or `true` | Return error; no cookie | `400 {"detail": "This confirmation link is invalid or has expired."}` |
| Supabase unavailable | `false` or `true` | Return error; no cookie | `503 {"detail": "Confirmation is unavailable. Try again later."}` |

Web UI states on `/auth/confirmed`:

| State | UI shown |
| --- | --- |
| Loading | Spinner card: "Confirming your email..." |
| `signed_in` (same browser) | Success card (`i-lucide-badge-check`): "Email confirmed" and "You are signed in as `<player_name>`." (or for `email_change`: "Email updated to `<email>`."), plus a primary **Continue to game** button (`/game`) and a secondary **Account settings** button (`/settings`). `usePlayerAuth().session` is updated immediately. |
| `confirmation_required` (different browser or scanner) | Confirmation card (`i-lucide-shield-check`): "Confirm your email" explaining that an extra click protects the link from automated email scanners, with a **Confirm email** button that submits `POST /api/v1/auth/confirm` with `confirm: true`. |
| `confirmed` (manual confirm succeeded) | Success card (`i-lucide-badge-check`): "Email confirmed" with description "Your email is verified. Sign in to continue." and a **Sign in** button (`/auth/login`). |
| Error / expired / missing params | Warning card (`i-lucide-mail-warning`): clear error message with **Resend confirmation** (or **Sign in**) action. |

To prevent Outlook Safe Links from consuming the token before the browser reaches `/auth/confirmed`, production Supabase email templates should link directly to `{{ .RedirectTo }}&token_hash={{ .TokenHash }}&type=signup` (and `type=recovery` / `type=email_change`). The gateway supports both `token_hash` and standard PKCE `code` links.

### 3. Password recovery (`POST /api/v1/auth/reset-password` and `/auth/reset-password`)

- `POST /api/v1/auth/recover` stores a recovery flow record (with `browser_hash` and `code_verifier`) and calls `reset_password_for_email(email, {"redirect_to": f"{WEB_BASE_URL}/auth/reset-password?flow={flow_id}"})`.
- `/auth/recover` validates the email field client-side with a Zod schema before calling the API.
- `/auth/reset-password` reads `code` / `token_hash` / `flow` / `error` from the URL on mount, immediately clears the query string with `router.replace`, and shows:
  - An error card with a **Request new link** button (`/auth/recover`) if `error` is present or both `code` and `token_hash` are missing.
  - Otherwise, a form with `PasswordStrengthField` (`new_password` + `confirm_password`, validated by `strongPasswordSchema`).
- Submitting the form calls `POST /api/v1/auth/reset-password` with `{ flow_id?, code?, token_hash?, new_password }`.
  - The gateway verifies the recovery token (`verify_otp(type="recovery")` for `token_hash`, or `exchange_code_for_session` with the stored `code_verifier` for `code`), updates the user's password via Supabase, signs out the Supabase session, revokes all existing gateway sessions for that account (`players.revoke_sessions(email, keep=None)`), purges trained models for that account, and deletes the flow record.
  - On success: `200 {"status": "password_reset"}`; the web client shows a success toast and navigates to `/auth/login`.
  - On invalid/expired link: `400 {"detail": "This recovery link is invalid or has expired."}`.
  - On Supabase outage: `503 {"detail": "Password reset is unavailable. Try again later."}`.

### 4. Email change confirmation

- `SupabasePlayerIdentity.request_email_change` passes `options={"email_redirect_to": f"{WEB_BASE_URL}/auth/confirmed?flow={flow_id}&intent=email_change"}` to `client.auth.update_user({"email": new_email}, ...)`.
- In `/settings`, the confirmation toast says: `"Check both your current and new inboxes to confirm the change, then sign in with your new address."`
- When `POST /api/v1/auth/confirm` completes an `email_change` on the same browser, `_open_verified()` runs the deferred `move_email()` migration immediately and issues a fresh session cookie for the new email, so the player is never stuck with a stale session.
- `POST /api/v1/auth/account/email` is rate-limited in production (`5 / 15 minutes` per account email) to prevent authenticated email enumeration.

### 5. Bug fixes and security hardening

- **No password trimming:** Remove `.trim()` from `password` in `usePlayerAuth.ts` (`signInWithPassword` and `registerAccount`). Passwords are sent verbatim everywhere.
- **Disambiguate `403` on `/auth/login`:** `loginFailure(statusCode, detail)` returns `'unconfirmed'` only when `statusCode === 403` **and** `detail` matches `"Confirm your email before signing in."`. Any other `403` (such as BotID `"Request blocked."`) returns `'blocked'` and displays the error toast instead of the unconfirmed-email banner.
- **Do not penalize `login_fail` on unconfirmed email:** `EmailNotConfirmedError` in `POST /auth/login` does not call `rate_limiter.record_failure("login_fail", ...)`.
- **Redis-backed brute-force limiting:** Replace in-memory-only `AttemptLimiter` checks in `POST /clearance` and `POST /auth/account/*` (`_reauthenticate`) with a Redis-backed limiter (sharing `container.rate_limiter` / Redis client when `REDIS_URL` is set, with in-memory fallback in development).
- **Do not mask outages on `/auth/register`:** `SupabasePlayerIdentity.register` masks only existing-account / conflict errors (`user_already_exists`, `email_exists`) as `202`. Timeouts, connection errors, and 5xx responses raise `IdentityUnavailableError`, which `POST /auth/register` maps to `503 {"detail": "Registration is unavailable. Try again later."}`.
- **BotID coverage and plugin order:** Add `POST /api/v1/auth/recover`, `POST /api/v1/auth/resend-confirmation`, `POST /api/v1/auth/confirm`, and `POST /api/v1/auth/reset-password` to `BOTID_PROTECTED_ROUTES` (and `botid_paths` in `main.py`). Set `enforce: 'pre'` on `apps/web/app/plugins/botid.client.ts`.
- **Expired player session cleanup:** `SupabasePlayerStore._insert_session` deletes expired rows (`expires_at <= now`) on insert, matching `SupabaseSessionStore`.
- **Production `WEB_BASE_URL` guard:** When `APP_ENV == "production"`, `build_container()` requires `WEB_BASE_URL` to be a non-localhost `http(s)` origin (not blank, not `localhost`, not `127.0.0.1`, not `::1`); otherwise it includes `WEB_BASE_URL` in `ConfigurationError`. Trailing slashes are stripped before building redirect URLs.
- **Admin clearance fetch scope:** Move `onMounted(loadAccess)` from `apps/web/app/app.vue` to `apps/web/app/layouts/dashboard.vue` so normal players do not call `GET /api/v1/clearance` on every page load.

## Acceptance criteria

### Confirmation & browser binding

- **API-AUTH-001**: Given a valid `shield_auth_browser` cookie on `POST /auth/register`, when Supabase returns confirmation-pending, then the gateway stores a flow record containing `sha256(cookie)` (never the raw cookie) and the PKCE `code_verifier`, passes `email_redirect_to = "<WEB_BASE_URL>/auth/confirmed?flow=<flow_id>"` to Supabase, and returns `202 {"status": "confirmation_sent"}`.
- **API-AUTH-002**: Given a stored signup flow and a `POST /auth/confirm` request with `confirm: false` carrying the matching `shield_auth_browser` cookie and valid `token_hash` (or PKCE `code`), then the gateway verifies with Supabase, signs out the Supabase session, deletes the flow record, sets the `shield_player_session` cookie, and returns `200 {"status": "signed_in", "session": ...}`.
- **API-AUTH-003**: Given a stored signup flow and a `POST /auth/confirm` request with `confirm: false` carrying a missing or different `shield_auth_browser` cookie (such as an email scanner or another browser), then the gateway does **not** call Supabase verify/exchange, does **not** consume the flow, sets no cookie, and returns `200 {"status": "confirmation_required"}`.
- **API-AUTH-004**: Given a different browser sending `POST /auth/confirm` with `confirm: true` and a valid `token_hash` (or `code`), then the gateway verifies the token with Supabase (for `token_hash`), signs out the Supabase session, sets **no** `shield_player_session` cookie, and returns `200 {"status": "confirmed"}`.
- **API-AUTH-005**: Given an invalid or expired `token_hash` or `code` on `POST /auth/confirm`, then the gateway returns `400` with no cookie; given Supabase unavailable, it returns `503`.
- **WEB-AUTH-001**: Given `/auth/confirmed?code=abc&flow=xyz`, when the page mounts, then it immediately strips sensitive query parameters from the URL via `replace`, sends `POST /auth/confirm` with `confirm: false`, and on `signed_in` updates `usePlayerAuth().session` and shows the signed-in confirmation UI with a link to `/game`.
- **WEB-AUTH-002**: Given `POST /auth/confirm` returns `confirmation_required`, then `/auth/confirmed` shows a manual confirmation screen with a **Confirm email** button; clicking it sends `POST /auth/confirm` with `confirm: true` and on `confirmed` shows the "Email confirmed" screen with a **Sign in** button.
- **WEB-AUTH-003**: Given `/auth/confirmed?error=access_denied&error_code=otp_expired` or `/auth/confirmed` with no `code` or `token_hash`, then the page never shows "Email confirmed" and instead shows an error/invalid-link state.
- **WEB-AUTH-004**: Given a browser without a `shield_auth_browser` cookie, when the client triggers register, resend, recover, or email change, then it sets a valid 32+ character URL-safe `shield_auth_browser` cookie before sending the request.

### Password recovery & email change

- **API-AUTH-006**: Given `POST /auth/recover`, then Supabase `reset_password_for_email` is called with `redirect_to = "<WEB_BASE_URL>/auth/reset-password?flow=<flow_id>"` and a recovery flow record is stored.
- **API-AUTH-007**: Given a valid recovery `token_hash` (or PKCE `code` with stored `code_verifier`) and a strong `new_password` on `POST /auth/reset-password`, then the gateway updates the password via Supabase, signs out the Supabase session, revokes all existing gateway sessions for that email, deletes the flow record, and returns `200 {"status": "password_reset"}`; given a weak password it returns `422`; given an invalid/expired token it returns `400`.
- **API-AUTH-008**: Given `POST /auth/account/email`, then `update_user` is called with `email_redirect_to = "<WEB_BASE_URL>/auth/confirmed?flow=<flow_id>&intent=email_change"`; and calling `POST /auth/account/email` more than 5 times in 15 minutes in production returns `429` with `Retry-After`.
- **WEB-AUTH-005**: Given `/auth/reset-password?token_hash=...&flow=...`, when the page mounts, then it strips the query parameters from the URL and renders a new-password form using `PasswordStrengthField`; submitting a valid password calls `POST /auth/reset-password` and navigates to `/auth/login` with a toast.
- **WEB-AUTH-006**: Given `/auth/recover`, then `UAuthForm` validates the email client-side with a Zod schema before submitting; and `/settings` email-change toast instructs the player to confirm in both their current and new inboxes.

### Bug fixes & security hardening

- **WEB-AUTH-007**: Given a password with leading or trailing spaces, when `signInWithPassword` or `registerAccount` is called, then the password is sent untrimmed to the gateway.
- **WEB-AUTH-008**: Given `POST /auth/login` fails with `403 {"detail": "Request blocked."}` (BotID), then `loginFailure` does not return `'unconfirmed'` and the login page shows an error toast instead of the "Confirm your email first" banner; given `403 {"detail": "Confirm your email before signing in."}`, it still shows the unconfirmed banner.
- **API-AUTH-009**: Given `APP_ENV="production"` and an unconfirmed user on `POST /auth/login`, when they submit the right password 11 times in 15 minutes, then `login_fail` does not lock out their email (`403`, not `429` from `login_fail`).
- **API-AUTH-010**: Given `APP_ENV="production"` and a shared Redis client, when failed attempts on `POST /clearance` or `POST /auth/account/*` (`_reauthenticate`) are split across two `Container` instances, then the combined count triggers `429` with `Retry-After`.
- **API-AUTH-011**: Given Supabase raises a 5xx or timeout error on `POST /auth/register`, then the gateway returns `503` (not `202`); given `user_already_exists` or `email_exists`, it still returns `202 {"status": "confirmation_sent"}`.
- **API-AUTH-012**: Given `APP_ENV="production"`, then `POST /auth/recover`, `POST /auth/resend-confirmation`, `POST /auth/confirm`, and `POST /auth/reset-password` require valid `x-shield-proxy-secret` and `x-shield-botid: pass`, and `BOTID_PROTECTED_ROUTES` in `apps/web` contains all 9 protected routes.
- **API-AUTH-013**: Given `SupabasePlayerStore._insert_session`, when a new session is inserted, then expired rows (`expires_at <= now`) in `players.sessions` are deleted.
- **API-AUTH-014**: Given `APP_ENV="production"` and `WEB_BASE_URL` blank or pointing to `localhost`/`127.0.0.1`, when `build_container` runs, then it raises `ConfigurationError` naming `WEB_BASE_URL`; trailing slashes on `WEB_BASE_URL` are stripped before constructing redirect URLs.
- **WEB-AUTH-009**: Given `apps/web/app/plugins/botid.client.ts`, then it registers with `enforce: 'pre'`; and `apps/web/app/app.vue` does not call `loadAccess()`, while `apps/web/app/layouts/dashboard.vue` calls `loadAccess()` on mount.
- **API-AUTH-015**: Given the OpenAPI contract, then `POST /api/v1/auth/confirm` and `POST /api/v1/auth/reset-password` and their request/response schemas are present, and `mise run contract` leaves no diff.

## Security & privacy considerations

- **Email scanner defence:** Automated scanners (Outlook Safe Links, Proofpoint) do not possess the originating browser's `shield_auth_browser` cookie and do not execute a human click on the confirmation screen. Requiring `confirm: true` on cookie mismatch prevents scanners from silently activating accounts or triggering unwanted state changes.
- **No cross-browser session fixation:** Auto-sign-in occurs **only** when `sha256(shield_auth_browser)` matches the stored `browser_hash` for that `flow_id` (constant-time compare). Opening a confirmation link on another device confirms the email after a click but never grants a session without entering the password.
- **No leaked tokens in URL or logs:** `/auth/confirmed` and `/auth/reset-password` strip query parameters on mount with `router.replace`. Flow records store only `sha256(cookie)` and expire after 1 hour.
- **Distributed brute-force defence:** Moving admin and account re-authentication attempt tracking to Redis closes the serverless cold-start bypass on Vercel.
- **Fail closed:** Missing `WEB_BASE_URL` in production fails at cold start; BotID failures return `503`/`403`; invalid/expired confirm or reset tokens return `400`.
- **Contract and doc updates:** Adding `/auth/confirm` and `/auth/reset-password` changes `contracts/shield-api.openapi.json` (`mise run contract`). Update `docs/reference/configuration.md`, `docs/reference/http-api.md`, and `apps/api/.env.example`.

## Evaluation impact

None. No scoring or classifier change.

## Open questions

None. Defaults proposed for review before accepting:

1. **Cookie name:** `shield_auth_browser` (non-`HttpOnly` so the client can ensure it exists before calling `/auth/register`, validated by the backend on `Cookie` header; never used as a session credential on its own).
2. **Supabase email templates:** The gateway supports both `token_hash` (scanner-proof template) and default PKCE `code` links. Updating the Supabase project's signup/recovery/email-change templates to `{{ .RedirectTo }}&token_hash={{ .TokenHash }}&type=<type>` is documented as a production setup step for full Outlook Safe Links protection.
3. **Spec 0027 overlap:** `API-VERIFY-002` (register masks Supabase exceptions) and `WEB-VERIFY-003` (static `/auth/confirmed`) are updated/superseded by `API-AUTH-011` and `WEB-AUTH-001`–`003` once this spec is accepted.

## Verification

### 2026-11-25 · commit 2fda7a6 (+ uncommitted changes)

- Criteria: API-AUTH-001, API-AUTH-002, API-AUTH-003, API-AUTH-004, API-AUTH-005, WEB-AUTH-001, WEB-AUTH-002, WEB-AUTH-003, WEB-AUTH-004, API-AUTH-006, API-AUTH-007, API-AUTH-008, WEB-AUTH-005, WEB-AUTH-006, WEB-AUTH-007, WEB-AUTH-008, API-AUTH-009, API-AUTH-010, API-AUTH-011, API-AUTH-012, API-AUTH-013, API-AUTH-014, WEB-AUTH-009, API-AUTH-015
- Red: 24 failing test(s) before implementation (`apps/api/tests/test_auth_flows_and_hardening.py::test_register_binds_browser_cookie_and_flow_id_in_redirect`, `apps/api/tests/test_auth_flows_and_hardening.py::test_confirm_same_browser_verifies_signs_in_and_clears_flow`, `apps/api/tests/test_auth_flows_and_hardening.py::test_confirm_different_or_missing_browser_cookie_requires_manual_confirmation`)
- Green: 36 passing test(s)
- Gate: `mise run check` passed
