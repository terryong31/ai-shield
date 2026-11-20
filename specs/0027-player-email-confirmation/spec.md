# 0027 — Player email confirmation

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-09
- **Related:** [0016 game engine](../0016-game-engine/spec.md) (API-GAME-007, WEB-GAME-012: player auth), [0012 clearance](../0012-clearance-sessions/spec.md) (admin accounts in Supabase Auth), [0024 domain schemas](../0024-domain-schema-storage/spec.md), [0025 account settings](../0025-account-settings/spec.md)

## Problem

`POST /api/v1/auth/register` writes the account to `players.accounts` (a PBKDF2
hash) and signs the player in at once. Nobody proves they own the email, so
anyone can register `someone-else@example.com`, take that name's saves and
scores, and block the real owner from registering later.

The router also calls Supabase Auth `sign_up`, `sign_in_with_password` and
`sign_in_anonymously` on every request "best effort" and discards the results
(`routers/auth.py`). With **Confirm email** on in the hosted project, `sign_up`
sends a confirmation email that nothing ever checks, and there are now two
password stores that can disagree (threat model, "Two identity systems").

## Goals

- With Supabase configured, a new player must click the confirmation link
  before they can sign in. Registering does not sign them in.
- Supabase Auth is the only place a player's password lives. The gateway keeps
  its own session cookie, profile (name, tier), quotas and saves.
- Registering never reveals whether an email already has an account.
- Players can ask for the confirmation email again.

## Non-goals

- Changing email or password from `/settings` (spec 0025).
- OAuth or magic-link sign-in.
- Email confirmation without Supabase. Local SQLite mode keeps today's
  immediate sign-in and is documented as development-only.
- Custom email templates or SMTP setup in code (a dashboard setting; see
  Security).
- `POST /auth/recover`: unchanged (it already calls Supabase
  `reset_password_for_email`).
- Equal response timing between new and existing emails on register; only the
  response body and headers must match.
- Back-filling Supabase users for existing `players.accounts` rows (see Profiles).

## Behaviour

### Identity provider

A new `PlayerIdentity` port, chosen in `container.py`:

| Implementation | When | Password lives in | Confirmation |
| --- | --- | --- | --- |
| `SupabasePlayerIdentity` | `SUPABASE_URL` and `SUPABASE_KEY` set | Supabase Auth | Required when the project has **Confirm email** on |
| `LocalPlayerIdentity` | otherwise | `players.accounts.password_hash` (PBKDF2, as today) | None (development only) |

In Supabase mode a stored `password_hash` (from before this spec) is never
checked, and a Supabase error never falls back to the local password path.
Each Supabase call uses a throwaway client, and any Supabase session it opens
is signed out straight away; the browser only ever gets the gateway's
`shield_player_session` cookie.

### Endpoints

| Route | Body | Supabase mode | Local mode |
| --- | --- | --- | --- |
| `POST /auth/register` | `{email, password, player_name?}` | `sign_up` with `email_redirect_to = WEB_BASE_URL + "/auth/confirmed"` and `player_name` in `user_metadata`. Returns **`202`** `{"status": "confirmation_sent"}`, **no cookie**, whether the email is new, unconfirmed or already registered. If the project has confirmation off (Supabase returns a session), the player is signed in as in local mode | `200 PlayerSessionStatus` and the cookie, as today; `409` for a taken email |
| `POST /auth/login` | `{email, password}` | `sign_in_with_password`. Success: upsert the profile row, create the gateway session, `200` + cookie. Unconfirmed email (Supabase error code `email_not_confirmed`): **`403`** `{"detail": "Confirm your email before signing in."}`. Wrong password or unknown email (`invalid_credentials`): `401` with one generic `detail`. Any other Supabase error or an outage: **`503`** `{"detail": "Sign-in is unavailable. Try again later."}` | As today |
| `POST /auth/resend-confirmation` (new) | `{email}` | `auth.resend({type: "signup", email, options: {email_redirect_to}})`; always `202` `{"status": "confirmation_sent"}`, even for unknown emails or Supabase errors | `202`, no email sent |
| `POST /auth/anonymous` | none | No Supabase call (the `sign_in_anonymously` mirror is removed) | unchanged |

`PlayerSessionStatus`, `/auth/session`, `/auth/logout`, `/auth/upgrade`,
quotas and saves are unchanged.

Request bodies keep today's limits (`email` 3 to 254 characters; `password` 6
to 512 on register, 1 to 512 on login), and `email` must also match
`^[^@\s]+@[^@\s]+\.[^@\s]+$`; anything else is `422` before Supabase is
called. New contract schemas: `PlayerConfirmationResponse = {status:
"confirmation_sent"}` (the `202` body of register and resend) and
`PlayerResendRequest = {email}`. `POST /auth/register` documents both `200
PlayerSessionStatus` and `202 PlayerConfirmationResponse`.

Assumption: with **Confirm email** on, Supabase `sign_up` for an existing
email returns an obfuscated user and no error, so register can answer the same
for new and existing emails without asking Supabase which it was.

### Profiles

`players.accounts` keeps `email`, `player_name`, `tier`, `created_at`.
`password_hash` and `salt` become nullable (migration), and Supabase mode
never writes them. On the first successful Supabase login for an email with no
row, a row is created with `tier = "free"` and `player_name` from
`user_metadata.player_name` (falling back to the part of the email before `@`).
An existing row keeps its name and tier.

Existing players (created before this spec) sign in through Supabase Auth too:
if the old mirror created their Supabase user they confirm it (or use resend);
if not, registering again creates it and their existing profile, saves and
scores are kept.

### Web client

- `/auth/register`: on `202`, show "Check your email" (`UEmpty` or `UAlert`)
  with the address and a **Resend email** button; do not navigate to `/`.
- `/auth/login`: on `403`, show "Confirm your email first" with **Resend
  email**.
- New `/auth/confirmed` page (the link's landing page): "Email confirmed" and a
  **Sign in** button to `/auth/login`. It reads nothing from the URL fragment
  and stores nothing.

### Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `WEB_BASE_URL` | `http://localhost:3000` | Public origin of the web client, used for `email_redirect_to`. Must be in the Supabase project's **Redirect URLs** allowlist |

## Acceptance criteria

- **API-VERIFY-001**: Given Supabase mode, when `POST /auth/register` is called with a new email, then Supabase `sign_up` is called with the password, `player_name` in `user_metadata` and `email_redirect_to` = `WEB_BASE_URL` + `/auth/confirmed`, and the response is `202 {"status": "confirmation_sent"}` with no `Set-Cookie`, no gateway session and no `players.accounts` password hash.
- **API-VERIFY-002**: Given Supabase mode, when `POST /auth/register` is called for an email that is already registered (confirmed or not), or Supabase raises, then the response is byte-for-byte the same `202` as API-VERIFY-001.
- **API-VERIFY-003**: Given Supabase mode and an unconfirmed user, when `POST /auth/login` is called with the right password, then it returns `403` with `detail` "Confirm your email before signing in." and no cookie; with a wrong password or unknown email it returns `401` with one generic `detail`.
- **API-VERIFY-004**: Given Supabase mode and a confirmed user with no profile row, when `POST /auth/login` succeeds, then a `players.accounts` row is created with `tier="free"`, null `password_hash`, and `player_name` from `user_metadata.player_name` (or the email's local part); given an existing row, its `player_name` and `tier` are kept.
- **API-VERIFY-010**: Given Supabase mode and a successful `POST /auth/login`, then the response is `200 PlayerSessionStatus` with the `shield_player_session` cookie, and the Supabase session opened by the check has been signed out.
- **API-VERIFY-011**: Given Supabase mode and Supabase raising anything other than `invalid_credentials` or `email_not_confirmed` on login, then `POST /auth/login` returns `503` with no cookie; and given a legacy row with a `password_hash`, a login whose password matches only that hash (not Supabase) returns `401`.
- **API-VERIFY-012**: Given an `email` that fails the pattern or length limits, or a password outside its limits, when register, login or resend is called, then it returns `422` and Supabase is not called.
- **API-VERIFY-013**: The committed contract has `POST /api/v1/auth/resend-confirmation` with `PlayerResendRequest` and a `202 PlayerConfirmationResponse`, register documents `200` and `202`, login documents `401`, `403` and `503`, and `mise run contract` leaves no diff.
- **API-VERIFY-005**: Given Supabase mode, when `POST /auth/resend-confirmation` is called for any email (known, unknown, or with Supabase raising), then it returns the same `202 {"status": "confirmation_sent"}`, and for a syntactically valid email it calls Supabase `resend` with `type="signup"` and the same `email_redirect_to`.
- **API-VERIFY-006**: Given Supabase mode where `sign_up` returns a session (confirmation off in the project), when `POST /auth/register` is called, then the player is signed in exactly as in local mode (`200` + cookie) and the Supabase session is signed out.
- **API-VERIFY-007**: Given local mode (no Supabase), register and login behave as before spec 0027 (`200` + cookie, `409` for a taken email, `401` for bad credentials), and `POST /auth/resend-confirmation` returns `202` without side effects.
- **API-VERIFY-008**: Given Supabase mode, `POST /auth/anonymous` makes no Supabase Auth call, and register, login and resend make only the calls named in API-VERIFY-001, 003, 005, 006 and 010 (checked with a fake Supabase client behind `SupabasePlayerIdentity`).
- **API-VERIFY-014**: Given Supabase mode, after register, login (right and wrong password) and resend, the password does not appear in the captured log output or in any SQLite file.
- **API-VERIFY-009**: A migration makes `players.accounts.password_hash` and `salt` nullable, and the SQLite player store mirrors it (API-SCHEMA-006).
- **WEB-VERIFY-001**: Given `/auth/register` receives `202`, then the page shows a "Check your email" state naming the address with a **Resend email** button that calls `POST /auth/resend-confirmation`, and does not navigate away or treat the player as signed in.
- **WEB-VERIFY-002**: Given `/auth/login` receives `403`, then it shows "Confirm your email first" with a **Resend email** button; given `401`, the existing error toast.
- **WEB-VERIFY-003**: `/auth/confirmed` shows an "Email confirmed" state with a **Sign in** button to `/auth/login`, and reads no token from the URL and writes no storage.

## Security & privacy considerations

- **Enumeration:** register and resend answer identically for every email
  (API-VERIFY-002, 005). Login reveals "unconfirmed" only after the correct
  password, which Supabase also does.
- **One password store:** in Supabase mode the gateway never sees a stored
  password hash; the PBKDF2 path stays only for local development.
- **Credentials stop at the gateway:** the browser gets no Supabase token; every
  Supabase session opened for a check is signed out.
- **Email sending limits:** Supabase's built-in mailer only sends a few emails an
  hour and, on newer projects, only to the project's team members. For real
  players, configure custom SMTP (Authentication → Emails → SMTP) in the
  dashboard. Without it, registrations from outside the team never get an email.
- **Redirect allowlist:** `WEB_BASE_URL/auth/confirmed` must be added to
  Authentication → URL Configuration → Redirect URLs, or Supabase falls back to
  the Site URL.
- **Rate limiting:** Supabase rate-limits sign-ups and resends per project; the
  gateway adds none here (still a known gap for `/auth/*`).

## Evaluation impact

None. No scoring or classifier change.

## Open questions

None. Decided while drafting (change any before accepting):

1. **Existing players** are not back-filled: they sign in through Supabase,
   confirm via resend if the old mirror created their user, or register again;
   their profile, saves and scores are kept.
2. **Local mode** keeps immediate sign-in, development only (a non-goal above).
3. **Spec 0025** (change email and password) will be revised to go through
   Supabase Auth after this spec is accepted.

## Verification

### 2026-11-10 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-VERIFY-001, API-VERIFY-002, API-VERIFY-003, API-VERIFY-004, API-VERIFY-010, API-VERIFY-011, API-VERIFY-012, API-VERIFY-013, API-VERIFY-005, API-VERIFY-006, API-VERIFY-007, API-VERIFY-008, API-VERIFY-014, API-VERIFY-009, WEB-VERIFY-001, WEB-VERIFY-002, WEB-VERIFY-003
- Red: 27 failing test(s) before implementation (`apps/api/tests/test_player_confirmation.py::test_register_sends_a_confirmation_email_and_signs_nobody_in`, `apps/api/tests/test_player_confirmation.py::test_register_answers_every_email_the_same`, `apps/api/tests/test_player_confirmation.py::test_login_needs_a_confirmed_email`)
- Green: 27 passing test(s)
- Gate: `mise run check` passed
