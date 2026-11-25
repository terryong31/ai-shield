# 0048 — Display name

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-25
- **Related:** [0025 account settings](../0025-account-settings/spec.md) (renaming was a non-goal there), [0044 leaderboard read scaling](../0044-leaderboard-read-scaling/spec.md)

## Problem

A player sets the display name at registration and cannot change it. The name is copied into
`players.accounts`, `players.sessions` and each `game.scores` row, and into Redis leaderboard data.

## Goals

- A signed-in player can change the display name in `/settings`.
- The new name shows on the leaderboard immediately, on every board.

## Non-goals

- Unique display names (scores belong to the email, spec 0025).
- Profanity filtering.

## Behaviour

`PATCH /api/v1/auth/account/profile` with `{ "player_name": string }` returns `200` and the session
status. No password is necessary: the change is reversible and gives no access.

| Case | Status |
| --- | --- |
| Anonymous, missing or expired session | `403` `Sign in to manage your account.` |
| Empty after trim, longer than 64 characters, or contains control or bidirectional-override characters | `422` |
| More than 5 changes in 15 minutes for one account (production) | `429` with `Retry-After` |
| Store error | `503`, not reported as done |

The gateway updates the account, then the sessions, then the score rows, then the leaderboard
cache. The account is the source of truth, so a retry repairs a partial update. If the Redis update
fails, the gateway deletes the board ready marker, so the board rebuilds from the store.

In `/settings`, the Account card has a `Display name` row with the current name and a `Change`
button. The button opens a modal with one input. Success shows a toast and updates the session.

## Acceptance criteria

- **API-NAME-001**: Given a signed-in player, when they send a valid name, then the response and the next `GET /auth/session` contain the trimmed name, also in their other sessions.
- **API-NAME-002**: Given a player with scores, when they change the name, then all boards and score lists show the new name, and rank and total score do not change.
- **API-NAME-003**: Given another player with the same old name, then that player's rows do not change.
- **API-NAME-004**: Given an anonymous or missing session, then the response is `403`; given an invalid name, then `422`; nothing changes.
- **API-NAME-005**: Given production and more than 5 changes in 15 minutes, then the response is `429` with `Retry-After`.
- **API-NAME-006**: Given a Redis failure during the update, then the request succeeds and the board rebuilds with the new name; given a store failure, then the response is `503`.
- **WEB-NAME-001**: Given `/settings` and a signed-in player, then the Account card shows the display name with a `Change` modal that validates 1 to 64 characters, calls the endpoint through `useShieldApi()`, and updates the session and the leaderboard.

## Security & privacy considerations

Control and bidirectional-override characters are refused to prevent leaderboard spoofing. Vue
escapes the name. The proxy blocks cross-site `PATCH` requests.

## Evaluation impact

None.

## Open questions

None.

## Verification

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: API-NAME-001, API-NAME-002, API-NAME-003, API-NAME-004, API-NAME-005, API-NAME-006, WEB-NAME-001
- Red: 20 failing test(s) before implementation (`apps/api/tests/test_display_name.py::test_rename_updates_the_session_and_the_other_devices`, `apps/api/tests/test_display_name.py::test_supabase_rename_updates_account_and_sessions`, `apps/api/tests/test_display_name.py::test_rename_moves_scores_to_the_new_name_and_keeps_rank`)
- Green: 20 passing test(s)
- Gate: `mise run check` passed
