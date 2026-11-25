# 0025 — Account settings

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-09
- **Related:** [0027 player email confirmation](../0027-player-email-confirmation/spec.md) (Supabase Auth owns passwords), [0016 game engine](../0016-game-engine/spec.md) (player auth, `/settings`), [0023 saved boards](../0023-game-saved-boards/spec.md), [0024 domain schemas](../0024-domain-schema-storage/spec.md)

## Problem

`/settings` (`pages/settings.vue`) only offers the theme. Signed-in players cannot
change their password or email, start over, or delete their account. Scores in
`game.scores` are keyed by `player_name`, which is not unique: two players with
the same name overwrite each other's best score, and "delete my scores" cannot
be done safely.

## Goals

- Signed-in players can change their password and email, reset their progress
  and delete their account from `/settings`, below `Theme`.
- Every action requires the current password; reset and delete also need an
  explicit confirmation.
- Scores belong to an account (by email), not to a display name.
- The same behaviour on all three player stores (in-memory, SQLite, Supabase).

## Non-goals

- Email verification for the new address. With Supabase the gateway sets the new
  address as confirmed through the admin API (the current password was just checked).
- Renaming the player name.
- Undo or a grace period for deletion.
- Resetting the daily run quota: neither reset nor delete (then re-register)
  may give the same email a fresh day's count.
- Claiming old scores that were recorded without an email; they stay on the
  leaderboard as they are and are never removed by these actions.

## Behaviour

### Settings page (`/settings`)

Below the `Theme` card, signed-in players see an `Account` card. Anonymous players
see `Sign in to manage your account` linking to `/auth/login` instead.

| Row | Control | Opens |
| --- | --- | --- |
| Email | current email + `Change` | modal: new email, current password |
| Password | `Change` | modal: current password, new password, confirm new password |
| Reset progress | `Reset` (warning) | modal: what is removed, current password, `Reset progress` |
| Delete account | `Delete` (error) | modal: what is removed, current password, type `DELETE`, `Delete account` |

Forms use Nuxt UI (`UModal` `#body`/`#footer`, `UForm`, `UFormField`, `UInput`)
and call the gateway only through `useShieldApi()`. Success shows a toast;
errors show the gateway's `detail` under the form.

### Endpoints (player session cookie required)

| Method & path | Body | Success |
| --- | --- | --- |
| `POST /api/v1/auth/account/password` | `current_password` (1–512), `new_password` (6–512) | `200` session status |
| `POST /api/v1/auth/account/email` | `new_email` (valid address, 3–254), `current_password` | `200` session status with the new email |
| `POST /api/v1/auth/account/reset-progress` | `current_password` | `200` `{"scores_removed": n, "boards_removed": m}` |
| `DELETE /api/v1/auth/account` | `current_password`, `confirm` (must be exactly `DELETE`) | `204`, session cookie cleared |

Errors, the same on every endpoint:

| Case | Status |
| --- | --- |
| No session cookie, an unknown or expired session, or an anonymous session | `403` `Sign in to manage your account.` |
| Wrong current password | `401` (nothing changes) |
| 5 wrong passwords for one account within 10 minutes | `429` until the window passes (reuses the failed-attempt limiter in `services/sessions.py`) |
| Body invalid (missing field, bad email, password too short, unknown field) | `422` |
| New password equals the current one, or new email equals the current one | `422` |
| New email already has an account | `409` (nothing changes) |
| Store error | `503` generic message; the action is not reported as done |

What each action touches:

| Data | Change email | Change password | Reset progress | Delete account |
| --- | --- | --- | --- | --- |
| `players.accounts` | email updated | hash + salt replaced | kept | deleted (last) |
| `players.sessions` | email updated | all others revoked | kept | all deleted |
| `players.daily_usage` | moved to the new email (see below) | kept | kept | **kept** |
| `game.saved_boards` | moved to the new email | kept | deleted | deleted |
| `game.scores` (rows with this email) | email updated | kept | deleted | deleted |
| `audit.*` | untouched | untouched | untouched | untouched |

- **Usage on email change:** today's usage moves with the account. If the new
  email already has usage rows (left by a deleted account), each day keeps the
  larger of the two counts, so moving never lowers a count.
- **Saved boards on email change:** the new email can have no saved boards (a
  deleted account's boards are deleted), so they move without conflict.
- **Order and partial failure:** each action changes dependents first and the
  account row last (delete: boards → scores → sessions → account; email change:
  scores → boards → usage → sessions → account). On Supabase these are
  separate calls with no transaction. A failure midway returns `503` and
  leaves the account able to sign in with its old credentials, and repeating
  the action finishes it.
- **Where the password lives (spec 0027):** with Supabase configured, Supabase
  Auth holds the password and email, and the `players.accounts` hash is never
  read or written. The current password is checked by signing in to Supabase
  (that session is signed out at once), and the change is made with the admin
  API on that user (`update_user_by_id` for password and email, `delete_user`
  for delete). Without Supabase, the PBKDF2 hash in `players.accounts` is used.
- **Supabase ordering:** password: Supabase first, then other gateway sessions
  are revoked. Email: Supabase first (`email_exists` → `409`, nothing changes);
  if the gateway move then fails, the Supabase email is set back to the old one
  and `503` is returned. Delete: gateway data first, the Supabase user last; if
  that last call fails, `503` is returned, the player can still sign in (a fresh
  empty profile), and deleting again finishes it.

### Score ownership

The migration `supabase/migrations/<timestamp>_account_score_email.sql` (created
with `mise run db:migration account_score_email`) adds a nullable `email`
column to `game.scores` and an index on `(email, level_id, score_version)`,
with no backfill. The SQLite `game.scores` table mirrors it (API-STORE-006).
Recorded wave scores store the player's email. The best-score upsert is keyed
by `(email, level_id, score_version)` for rows with an email, so two accounts
with the same name each keep their own best score. `GET /api/v1/game/scores`
never returns the email.

### Contract and store interface

New request and response models in `shield_api/schemas.py` (`mise run contract`).
New `PlayerStore` methods: `change_password`, `change_email`,
`reset_progress`, `delete_account`; `AuditLog` gains
`delete_scores_for(email)` and `rename_scores_email(old, new)`. Supabase
parity is verified against the fake client in `tests/conftest.py`; tests make
no network calls.

## Acceptance criteria

Password

- **API-ACCOUNT-001**: Given a signed-in player, when they change their password with the correct current password, then `200` is returned and logging in with the new password succeeds while the old one returns `401`.
- **API-ACCOUNT-002**: Given a player signed in on two sessions, when they change their password on one, then that session keeps working and the other session is revoked.

Email

- **API-ACCOUNT-003**: Given a signed-in player, when they change their email to an unused valid address with the correct password, then `200` returns the new trimmed, lower-cased email, login works with the new email and returns `401` with the old one, and their saved boards, today's usage, sessions and scores follow the new email.
- **API-ACCOUNT-004**: Given a signed-in player, when the new email already has an account, then `409` is returned and nothing changes; when it equals the current email, then `422` is returned.
- **API-ACCOUNT-005**: Given usage rows left on an email by a deleted account, when another player moves to that email, then each day's counts are the larger of the two.

Reset progress

- **API-ACCOUNT-006**: Given a signed-in player with scores and saved boards, when they reset progress with the correct password, then their scores (matched by email) and saved boards are deleted, the removed counts are returned, and the account, tier, session and today's usage are unchanged.
- **API-ACCOUNT-007**: Given two accounts with the same player name that both recorded a score on the same level, when one resets progress, then the other's score remains on the leaderboard, and scores recorded without an email are never removed.

Delete account

- **API-ACCOUNT-008**: Given a signed-in player, when they delete their account with the correct password and `confirm: "DELETE"`, then `204` is returned with the session cookie cleared, and the account, its sessions, saved boards and scores are gone, so login returns `401`.
- **API-ACCOUNT-009**: Given a deleted account that used runs today, when the same email registers again the same day, then its used run counts are unchanged.
- **API-ACCOUNT-010**: Given a delete request whose `confirm` is anything other than exactly `DELETE`, then `422` is returned and nothing is deleted.

Errors and safety (all four endpoints)

- **API-ACCOUNT-011**: Given no session cookie, an unknown session or an anonymous session, when any account endpoint is called, then `403` is returned and nothing changes.
- **API-ACCOUNT-012**: Given a wrong current password, when any account endpoint is called, then `401` is returned and nothing changes; and after 5 wrong passwords for one account within 10 minutes, then the next call returns `429` even with the right password.
- **API-ACCOUNT-013**: Given an invalid body (missing field, malformed email, password under 6 characters, unknown field) or a new password equal to the current one, when an account endpoint is called, then `422` is returned.
- **API-ACCOUNT-014**: Given any account request, when it succeeds or fails, then no response body contains a password or password hash, and no captured log record (`caplog`) contains the submitted passwords.
- **API-ACCOUNT-015**: Given a store that raises midway through deleting an account or changing an email, when the request runs, then `503` is returned and the player can still sign in with their old email and password.

Storage

- **API-ACCOUNT-016**: Given the in-memory and Supabase (fake client) player and score stores, when the same sequence of account actions runs against each, then their results match.
- **API-ACCOUNT-017**: Given the new migration, when a signed-in player's wave score is recorded, then the row stores their email, and the best-score upsert is keyed by email, level and score version.
- **API-ACCOUNT-018**: Given recorded scores with emails, when `GET /api/v1/game/scores` is called, then no row in the response contains an email.

Supabase Auth (spec 0027)

- **API-ACCOUNT-019**: Given Supabase mode, when a player changes their password with the right current password, then the current password is checked by a Supabase sign-in whose session is signed out, the new password is set with the admin API on that user, signing in with the old password returns `401` and with the new one `200`, and `players.accounts.password_hash` stays empty.
- **API-ACCOUNT-020**: Given a signed-in player, when they change their email, then the new address must be confirmed through Supabase's confirm-change flow and the gateway data moves at the first sign-in after confirmation ([spec 0042](../0042-run-spend-and-account-integrity/spec.md)); when Supabase reports the address is taken, then `409` is returned and nothing changes.
- **API-ACCOUNT-021**: Given Supabase mode, when a player deletes their account, then the gateway data is removed and then the Supabase user is deleted, so signing in returns `401`; when deleting the Supabase user fails, then `503` is returned.

Web

- **WEB-ACCOUNT-001**: Given a signed-in player on `/settings`, when the page renders, then an `Account` card below `Theme` shows their email with `Change`, `Password` with `Change`, `Reset progress` and `Delete account`; an anonymous player sees `Sign in to manage your account` linking to `/auth/login` instead.
- **WEB-ACCOUNT-002**: Given the email and password modals, when they are submitted, then they call `useShieldApi()` account methods, show the gateway's `detail` on error, and the password modal refuses to submit while the two new passwords differ.
- **WEB-ACCOUNT-003**: Given the reset and delete modals, when they open, then they list what will be removed and require the current password, and `Delete account` stays disabled until `DELETE` is typed.
- **WEB-ACCOUNT-004**: Given a successful reset, then a toast confirms it and the player stays on `/settings`; given a successful delete, then the player is signed out and returned to `/` as a new anonymous player.

## Security & privacy considerations

- Re-authentication: every action needs the current password, so a stolen
  session cookie alone cannot take over (email), lock out (password) or wipe
  (reset, delete) an account.
- Brute force: the re-auth check would otherwise be a password oracle for a
  cookie holder; 5 failures per account per 10 minutes returns `429`.
- A password change revokes other sessions, so a leaked session stops working.
- Passwords travel only in request bodies, are checked by Supabase Auth (or,
  without Supabase, against the PBKDF2 hash in constant time), and are never
  logged, stored in clear or echoed.
- Deletion removes the email, hash, sessions, boards and scores. Usage rows
  (email, date and counts only) are kept so the quota cannot be reset; audit
  rows hold no account email and are kept.
- Fail closed: a store error returns `503`; partial Supabase state never leaves
  the account unable to sign in (account row changes last).

## Evaluation impact

None. No engine or detection change.

## Open questions

None. Decisions taken in this draft that the owner may overturn before accepting:
ordered best-effort writes on Supabase instead of one Postgres function per
action; deleted accounts' scores leave the leaderboard; old email-less scores
are left as they are; usage rows survive deletion.

## Verification

### 2026-11-10 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-ACCOUNT-001, API-ACCOUNT-002, API-ACCOUNT-003, API-ACCOUNT-004, API-ACCOUNT-005, API-ACCOUNT-006, API-ACCOUNT-007, API-ACCOUNT-008, API-ACCOUNT-009, API-ACCOUNT-010, API-ACCOUNT-011, API-ACCOUNT-012, API-ACCOUNT-013, API-ACCOUNT-014, API-ACCOUNT-015, API-ACCOUNT-016, API-ACCOUNT-017, API-ACCOUNT-018, API-ACCOUNT-019, API-ACCOUNT-020, API-ACCOUNT-021, WEB-ACCOUNT-001, WEB-ACCOUNT-002, WEB-ACCOUNT-003, WEB-ACCOUNT-004
- Red: 34 failing test(s) before implementation (`apps/api/tests/test_account_settings.py::test_change_password_swaps_the_working_password`, `apps/api/tests/test_account_settings.py::test_change_password_revokes_the_other_sessions`, `apps/api/tests/test_account_settings.py::test_change_email_moves_everything_to_the_new_address`)
- Green: 34 passing test(s)
- Gate: `mise run check` passed
