# 0052 — Anonymous draft persistence and server-side score promotion

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-26
- **Related:** [ADR 0004](../../docs/explanation/decisions/0004-frontend-talks-only-to-gateway.md), [0023-game-saved-boards](../0023-game-saved-boards/spec.md), [0033-saved-board-return-and-loading](../0033-saved-board-return-and-loading/spec.md), [0044-leaderboard-read-scaling](../0044-leaderboard-read-scaling/spec.md), [0047-auth-flows-and-hardening](../0047-auth-flows-and-hardening/spec.md)

## Problem

Anonymous players can open the game, wire a board, and beat levels immediately, but their progress is lost as soon as they reload the page or create an account:

1. **Board layouts live only in page memory.** Refreshing the page or navigating to `/auth/login` or `/auth/register` resets the board to the starter board.
2. **Earned scores, medals, and mastery are discarded.** `POST /api/v1/game/run` only records scores when `player.can_record_scores` is true (signed-in players). If an anonymous player beats a level and then signs up to save their progress, they must replay the level from scratch.
3. **Client-side storage cannot be trusted for scores.** Putting scores, medals, or level completions in `localStorage` would let a user forge maximum points and medals in browser DevTools.
4. **Stale anonymous usage rows accumulate.** While `players.sessions` prunes expired rows on insert (spec 0047), `players.daily_usage` keeps old `anon:<hash>` rows from past UTC days indefinitely.

At the same time, `ai-shield` uses a gateway-owned session architecture (ADR 0004) where Supabase Auth verifies passwords and email confirmation only, and `POST /api/v1/auth/anonymous` creates a lightweight gateway session in `players.sessions` without calling Supabase Auth. Using Supabase Anonymous Sign-In would add `auth.users` MAU costs, shared-gateway-IP rate-limit collisions, and an `email`-to-UUID schema migration without solving existing-account merges.

## Goals

- Separate **non-authoritative UI drafts** from **authoritative game results**:
  - Persist anonymous players' unsaved board layouts and node positions per level in `localStorage` so edits survive reloads and auth navigation.
  - Persist anonymous players' server-evaluated scores, medals, wins, and mastery **server-side** (keyed by the `HttpOnly` anonymous session token hash) so clients can never forge scores or medals.
- Promote both on sign-in or same-browser registration confirmation:
  - Promote server-side anonymous scores into `game.scores` (keeping the best score per level) and update the leaderboard.
  - Promote local board drafts into `PUT /api/v1/game/saves/{level_id}` without silently overwriting an existing server save.
- Keep `POST /api/v1/auth/anonymous` free of Supabase Auth calls and preserve OWASP session regeneration on sign-in.
- Prune stale anonymous rows in `game.anonymous_scores` and `players.daily_usage` so database storage does not grow without bound.

## Non-goals

- Calling Supabase Anonymous Sign-In (`sign_in_anonymously()`) or creating `auth.users` rows for anonymous visitors.
- Showing anonymous players on the public leaderboard before they sign in.
- Cross-device sync of anonymous drafts or anonymous scores before sign-in.
- Storing API keys, credentials, or `custom` sandbox secrets in `localStorage`.
- Multiple named draft slots per level (one local draft per `level_id`).

## Behaviour

### 1. Local board draft storage (`apps/web`, non-authoritative)

When the active player is anonymous (`session.is_anonymous === true`), the game client auto-saves board wiring and node positions to `localStorage` under a versioned key per level. **Scores, medals, wins, and mastery are never stored in or read from `localStorage`.**

- **Key format:** `shield_anon_draft:v1:<level_id>` (for example, `shield_anon_draft:v1:easy-1`).
- **Payload shape:**
  ```json
  {
    "version": 1,
    "level_id": "easy-1",
    "updated_at": "2026-11-26T12:00:00.000Z",
    "board": { "nodes": [], "edges": [] },
    "positions": { "incoming": { "x": 0, "y": 120 } }
  }
  ```
- **Write rules:**
  - Writes are debounced (for example, 400 ms after the last board or position change).
  - Drafts are only written for non-`custom` campaign levels. Never write API keys or any `custom` secret fields.
  - Enforce the same structural limits as spec 0023 (at most 60 nodes, 200 edges, and 256 KB serialized). If a draft exceeds these limits or `localStorage` throws (private mode, quota exceeded), fail silently without crashing the game UI.
- **Load and reset rules:**
  - When an anonymous player opens a level, load the matching local draft if present and valid; otherwise load the starter board.
  - If a stored draft is malformed JSON, has an unknown `version`, or references removed/invalid node kinds, discard it, fall back to the starter board, and show a non-blocking toast.
  - Clicking **Restart** resets the board on screen to the starter board and removes `shield_anon_draft:v1:<level_id>`.

### 2. Server-side anonymous scores (`apps/api`, authoritative)

Scores, medals, wins, and mastery for anonymous players are recorded **only by the gateway** from real `POST /api/v1/game/run` evaluations. There is no HTTP endpoint that accepts a score or medal from the browser.

- **Storage (`game.anonymous_scores`):**
  - New migration table in schema `game` (RLS enabled, deny-all for `public`/`anon`/`authenticated`, `service_role` only, matching ADR 0004):
    - Primary key: `(session_token_hash, level_id, score_version)`
    - Columns: `session_token_hash` (text), `level_id` (text), `score_version` (integer), `total_score` (integer), `medal` (text), `attacks_blocked` (integer), `attacks_total` (integer), `false_alarms` (integer), `avg_latency_ms` (double precision), `total_cost_usd` (double precision), `board_json` (jsonb), `won` (boolean), `mastered` (boolean), `created_at` (timestamptz), `expires_at` (timestamptz).
- **Recording on `POST /api/v1/game/run`:**
  - When `not is_custom_test`, `recordable` (`result.agent_mode in ("live", "none")`), and the caller has an authenticated anonymous session (`player.authenticated and player.is_anonymous` with a valid `shield_player_session` cookie):
    - Upsert the run into `game.anonymous_scores` keyed by `(sha256(token), level_id, current_score_version)`, keeping the better run using the same ranking rules as `game.scores` (higher `total_score`, then lower `avg_latency_ms`, then lower `total_cost_usd`, preserving `won`/`mastered` improvements).
    - Set `expires_at = now() + interval '7 days'`.
    - Do **not** write to `game.scores` or the public Redis leaderboard while anonymous.
- **Reading anonymous progress (`GET /api/v1/game/progress` or existing progress endpoint):**
  - If the caller has an authenticated anonymous session, return their pending wins/medals/best scores from `game.anonymous_scores` so the level-select UI can display their earned medals across reloads without trusting client storage.
  - Never include `game.anonymous_scores` in `GET /api/v1/game/leaderboard`.

### 3. Promotion on sign-in or registration confirmation

When a player signs in (`POST /api/v1/auth/login`) or completes same-browser confirmation (`POST /api/v1/auth/confirm` returning `signed_in`), `_open_verified` runs on the gateway:

1. **Server-side score promotion (`apps/api`):**
   - Inspect the incoming `shield_player_session` cookie (`previous`) **before** revoking it.
   - Verify that `previous` maps to a live, non-expired `is_anonymous = true` row in `players.sessions`. (Never promote from an expired session or from another signed-in user's session.)
   - Fetch all non-expired rows in `game.anonymous_scores` for `sha256(previous)`.
   - For each row, promote it into `game.scores` via `container.scores.record_score_change(...)` using the newly signed-in player's `email` and `player_name`, and update the leaderboard via `container.leaderboard.on_score_recorded(player.email, change)`. Because `record_score_change` keeps the best score per `(email, level_id, score_version)`, an existing account's higher score is never downgraded by a lower anonymous score.
   - Delete all `game.anonymous_scores` rows for `sha256(previous)`.
   - Revoke `previous` and issue a brand-new `shield_player_session` cookie (preserving OWASP session fixation protection).
   - If score promotion fails due to a transient storage error, log the error and fail safe without blocking sign-in (or roll back cleanly according to the open question below).

2. **Client-side board draft promotion (`apps/web`):**
   - When the now-signed-in player opens a level that has a local draft in `localStorage`:

| Server state for `level_id` | Local draft exists? | Client action |
| --- | --- | --- |
| No server save (`404`) | Yes | Automatically upload the local draft via `PUT /api/v1/game/saves/{level_id}`. On `200`, remove the local draft and show a toast: `"Your local board was saved to your account."` |
| Server save exists (`200`) | Yes | Do **not** overwrite the server save automatically. Show a prompt with two choices: **Keep local board** (uploads via `PUT`, removes local draft) or **Use saved board** (loads server save, removes local draft). |
| Server save exists (`200`) or `404` | No | Normal signed-in load behaviour (spec 0023 / 0033). |
| Level forbidden for tier (`403`, e.g., `custom` or `pro` on `free`) | Yes | Skip promotion for that level without showing an error and leave/clear local draft safely. |
| Network / `5xx` error during promotion | Yes | Keep the local draft in `localStorage` so no work is lost, and show a non-blocking warning toast. |

- Signing out never copies a signed-in player's board into anonymous `localStorage`.

### 4. Stale anonymous data cleanup (`apps/api`)

- When `SupabasePlayerStore._insert_session` runs (or on anonymous session creation), delete:
  - Expired rows in `game.anonymous_scores` where `expires_at <= now()`.
  - Stale anonymous rows in `players.daily_usage` where `email LIKE 'anon:%'` and `usage_date < (current UTC date - 7 days)`.
- Signed-in player rows in `players.daily_usage` and `game.scores` are never deleted by this cleanup.

## Acceptance criteria

### Board drafts (`apps/web`)

- **WEB-DRAFT-001**: Given an anonymous player edits a board on a campaign level and waits past the debounce window, when they reload the page or reopen that level, then their edited board and node positions are restored from `localStorage`.
- **WEB-DRAFT-002**: Given an anonymous player clicks **Restart** on a level with a local draft, then the board resets to the starter board and the local draft key for that level is removed from `localStorage`.
- **WEB-DRAFT-003**: Given corrupt JSON, an unsupported version, or an unavailable `localStorage` (`QuotaExceededError` / `SecurityError`), when an anonymous player opens or edits a level, then the page falls back cleanly to the starter board without throwing an uncaught error.
- **WEB-DRAFT-004**: Given an anonymous player has a local draft for a level and signs in (or confirms registration) to an account with no server save (`404`) for that level, when the level loads, then the client uploads the draft via `PUT /api/v1/game/saves/{level_id}`, clears the local draft on `200`, and displays a confirmation toast.
- **WEB-DRAFT-005**: Given an anonymous player has a local draft for a level and signs in to an account that already has a server save (`200`) for that level, when the level loads, then the client does not overwrite the server save automatically and prompts the player to choose **Keep local board** or **Use saved board**; choosing either updates the state and clears the local draft.
- **WEB-DRAFT-006**: Given automatic draft promotion fails with a `5xx` or network error, then the local draft remains intact in `localStorage` so the player's work is not lost.
- **WEB-DRAFT-007**: Given a signed-in player signs out, then their board is not written to anonymous `localStorage`.

### Server-side anonymous scores and cleanup (`apps/api`)

- **API-ANONSCORE-001**: Given an authenticated anonymous player completes a recordable campaign wave on `POST /api/v1/game/run`, then the gateway stores the best server-evaluated score, medal, win, and mastery in `game.anonymous_scores` keyed by `sha256(token)`, does not write to `game.scores`, and does not show the player on `GET /api/v1/game/leaderboard`.
- **API-ANONSCORE-002**: Given an anonymous session with pending rows in `game.anonymous_scores`, when that browser signs in via `POST /api/v1/auth/login` or completes same-browser `POST /api/v1/auth/confirm`, then `_open_verified` promotes those rows into `game.scores`, updates the leaderboard, deletes the `game.anonymous_scores` rows for that session, revokes the old anonymous session token, and issues a new `shield_player_session` cookie.
- **API-ANONSCORE-003**: Given an existing signed-in account already has a higher score for a level than the anonymous session being promoted, when the player signs in, then the existing higher score in `game.scores` is preserved; when the anonymous score is higher, `game.scores` and the leaderboard update to the higher score.
- **API-ANONSCORE-004**: Given an expired anonymous session cookie or a signed-in session cookie from another user, when `_open_verified` runs, then no rows from `game.anonymous_scores` are promoted.
- **API-ANONSCORE-005**: Given a tampered `localStorage` entry containing arbitrary `score`, `medal`, `won`, or `mastered` fields, when the player loads or promotes a board draft, then those fields are ignored and rejected by `PUT /api/v1/game/saves/{level_id}` (`422` if sent), and `game.scores` is never modified by client-submitted scores.
- **API-DRAFT-001**: Given `SupabasePlayerStore._insert_session` runs when `game.anonymous_scores` has expired rows and `players.daily_usage` has `anon:<hash>` rows older than 7 UTC days alongside recent anonymous rows and old signed-in user rows, then only expired `game.anonymous_scores` rows and `anon:%` daily usage rows older than 7 UTC days are deleted.

## Security & privacy considerations

- **Tamper-proof scores and medals:** Scores, medals, wins, and mastery are computed exclusively on the server during `POST /api/v1/game/run` and stored in `game.anonymous_scores` keyed by the `HttpOnly` session cookie's SHA-256 hash. Manipulating `localStorage` cannot grant stars, medals, or points.
- **No session fixation (OWASP):** Anonymous sessions are never upgraded in place; `_open_verified` revokes the old anonymous session and issues a brand-new `HttpOnly` cookie on sign-in/confirmation after promoting scores.
- **Cross-user isolation:** Promotion checks that the incoming cookie belongs to a live, non-expired `is_anonymous = true` session before moving rows, and deletes the anonymous score rows immediately so they cannot be replayed into a second account.
- **No secret persistence:** `localStorage` holds only board topology and node positions for non-custom levels; no API keys, session tokens, or emails are stored client-side.
- **Untrusted client input:** Promoted board drafts go through `PUT /api/v1/game/saves/{level_id}` validation (`422` / `413` / `403`).
- **Database hygiene:** `game.anonymous_scores` is bounded by BotID + `30/hour` IP rate limiting on `/auth/anonymous`, one row per `(session_token_hash, level_id, score_version)`, and automatic 7-day expiry pruning.

## Evaluation impact

None. No engine, scoring, or classifier change.

## Decisions (2026-11-27)

The open questions below were answered when the spec was built:

- **Easy-level session:** the game page already starts an anonymous session on mount when there is none, so Easy wins are recorded in `game.anonymous_scores` with no extra call.
- **Promotion timing:** a draft is promoted when the signed-in player opens its level, so the choice prompt shows in context.
- **Different-browser confirmation:** accepted. Browser A promotes its scores at its next sign-in, while its anonymous session is still live.
- **Local draft TTL:** none. A draft stays until `Restart`, promotion, or the browser clears it.
- **Promotion order:** the gateway checks the old cookie before it revokes it, and moves the scores after the new session exists, so the scores take the account's display name.

## Open questions

- **Easy-level anonymous session creation:** Model-free levels (for example, `easy-1`) currently run without requiring an anonymous session cookie. Should the web client lazily call `POST /api/v1/auth/anonymous` before running a campaign wave so Easy wins are also captured in `game.anonymous_scores`? (Recommended: yes, on first wave run when unauthenticated, so anonymous Easy wins promote on sign-up too.)
- **Board draft promotion timing:** Should board draft promotion run lazily when the player opens each level (recommended, so the conflict prompt appears in context) or for all levels immediately after sign-in?
- **Different-browser email confirmation:** If a user plays anonymously in Browser A, registers, and clicks the confirmation link in Browser B (manual confirmation, spec 0047), Browser B does not have Browser A's anonymous cookie. When they return to Browser A and sign in via `/auth/login`, Browser A still has its anonymous cookie and scores will promote then — confirm this behaviour is acceptable.
- **Local draft TTL:** Should anonymous local board drafts expire client-side after a TTL (for example, 30 days) on read?

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: WEB-DRAFT-001, WEB-DRAFT-002, WEB-DRAFT-003, WEB-DRAFT-004, WEB-DRAFT-005, WEB-DRAFT-006, WEB-DRAFT-007, API-ANONSCORE-001, API-ANONSCORE-002, API-ANONSCORE-003, API-ANONSCORE-004, API-ANONSCORE-005, API-DRAFT-001
- Red: 13 failing test(s) before implementation (`/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/anonDraft.test.ts`, `/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/anonDraft.test.ts`, `/Users/terryong/Desktop/nuxt-projects/ai-shield/apps/web/test/anonDraft.test.ts`)
- Green: 18 passing test(s)
- Gate: `mise run check` passed

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: API-DRAFT-001
- Red: 1 failing test(s) before implementation (`apps/api/tests/test_anonymous_scores.py::test_cleanup_failure_never_blocks_a_session_and_runs_at_most_every_few_minutes`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
