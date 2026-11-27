# 0042 — Run spend and account integrity

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-23
- **Related:** [0016-game-engine](../0016-game-engine/spec.md) (API-GAME-007), [0020-game-ai-agent](../0020-game-ai-agent/spec.md) (quotas), [0022-game-custom-sandbox](../0022-game-custom-sandbox/spec.md), [0025-account-settings](../0025-account-settings/spec.md), [0027-player-email-confirmation](../0027-player-email-confirmation/spec.md), [0043](../0043-rate-limiting-and-client-ip/spec.md) (rate limits, client IP, Vercel BotID)

## Problem

A security review of the gateway found ways to spend the server's model budget
without limit, and to forge plan tier, scores and email ownership:

1. **No-session runs skip quota.** `PlayersStore.lookup(None)` returns an
   unauthenticated anonymous status; `_usage_key` then returns `None`, so
   `check_run` / `consume_run` skip every limit (`services/players.py`
   `_usage_key`, `check_run`, `consume_run`). `POST /game/run` without a cookie
   runs a Medium/Hard level's live agent on the server model forever.
2. **Cycling anonymous sessions resets quota.** `POST /auth/anonymous` mints a
   new session on every call, and anonymous usage is keyed by the hashed
   session token, so a new cookie is a fresh daily quota.
3. **Unbounded request size.** `GameRunRequest.custom_message` has no length cap
   and `/game/run` has no node/edge cap (only saves are capped at
   `SAVE_MAX_NODES = 60` / `SAVE_MAX_EDGES = 200`).
4. **AI check nodes on model-free levels are free.** `counts_quota` is
   `level.agent is not None`, so a signed-in player can wire `safety_check` /
   `llm_review` on an Easy level and call the server model with no quota.
5. **Custom (BYOK) mode bills the server key.** `_run_custom` receives
   `check_model=container.game_agent`, so `safety_check` / `llm_review` nodes in
   the sandbox run on the server's key, uncounted (`routers/game.py`).
6. **Free self-upgrade.** `POST /auth/upgrade` makes any signed-in player
   `paid` with no payment. There is no payment system.
7. **Forged scores.** `POST /game/scores` lets any signed-in player record any
   score. `/game/run` already records scores server-side; the web client never
   calls `submitScore` (`useShieldApi.ts`).
8. **Unverified email change.** `SupabasePlayerIdentity.update_email` sets
   `email_confirm: True`, so a player can move their account (and later receive
   password resets) to an address they do not control
   (`services/identity.py`).

## Goals

- Every `/game/run` that can call a server-side model is charged to a session
  and nothing else reaches the server model.
- Request size on `/game/run` is bounded.
- Custom mode never uses the server's model key.
- Plan tier, scores and email ownership cannot be self-asserted.

## Non-goals

- `POST /game/train` (discussed separately).
- A payment system. Self-upgrade stays available only behind a setting for demos.
- Per-minute rate limiting (spec 0043) and leaderboard caching (spec 0044).
- Changing tier quota numbers (`DAILY_LIMITS`).

## Behaviour

### "Model run"

A `/game/run` request is a **model run** when it can call a server-side model
or paid API: the level has an agent (`level.agent is not None`), **or** the
board contains a `safety_check`, `llm_review` or `jev` node (the Jev API uses
the server's key). Custom mode is never a model run (it uses the player's key
only; see API-SPEND-011 for its check nodes). Classification-only runs on Easy
levels with none of those nodes stay free and need no session.

A model run needs a player session (anonymous is fine) and counts against the
daily quota. With no session the gateway answers `401`; the web client then
calls `POST /auth/anonymous` and retries the run once.

To prevent concurrent requests from bypassing the daily cap, `POST /game/run`
atomically reserves 1 quota slot (`players.reserve_daily_usage` RPC / lock)
**before** calling any model, and releases the reserved slot
(`players.release_daily_usage`) if board execution fails with `422` or `502`/`503`.

### `/game/run`

| Request | Before | After |
| --- | --- | --- |
| Model run, no session cookie (or unknown / expired token) | runs, uncounted | `401` `"Start a session to play this level."`; no model call |
| Model run, anonymous session | counted per session | counted per session (1 wave / 3 tests a day, unchanged) |
| Easy level, `safety_check` / `llm_review` / `jev` node, signed-in | runs, uncounted | counted against the player's daily quota |
| Easy level, `jev` node, no session | runs, uncounted | `401` (as any model run) |
| `custom_message` longer than 1000 characters | accepted | `422` (schema validation) |
| Board with more than 60 nodes or 200 edges | accepted | `422` `"A board holds at most 60 nodes and 200 wires."` |
| Custom mode with `safety_check` / `llm_review` | server key | player's BYOK model; server model never called |

### Anonymous abuse (cookie cycling)

Anonymous usage stays keyed per session (1 wave / 3 tests a day). Minting new
anonymous sessions to reset that quota is handled in spec 0043, not here: at
most 30 `POST /auth/anonymous` per IP per hour, and Vercel BotID on
`/auth/anonymous`, `/auth/register`, `/auth/login`, `/game/run` and
`/game/train`. There is **no** per-IP daily run cap and no
`ANONYMOUS_IP_DAILY_*` setting.

### `POST /auth/upgrade`

New setting `ALLOW_SELF_UPGRADE: bool = False`.

| `ALLOW_SELF_UPGRADE` | Signed-in free player | Anonymous |
| --- | --- | --- |
| `False` (default) | `403` `"Paid plans are not available yet."`; tier unchanged | `403` |
| `True` | `200`, tier `paid` (today's behaviour) | `403` (today's behaviour) |

`GET /game/levels` (`GameCatalogResponse`) gains `self_upgrade_enabled: bool`.
The plans page shows the Paid card's button disabled with the label
"Coming soon" when it is `false`.

### `POST /game/scores`

Removed. The route answers `405 Method Not Allowed` (GET and DELETE on the same
path stay). `submitScore` is removed from `useShieldApi()`. Scores are recorded
only by `/game/run`.

### `POST /account/email` (Supabase identity)

The gateway no longer auto-confirms. It signs in as the player (password just
re-checked) and calls the user-session `auth.update_user({"email": new})`, so
Supabase sends its confirm-change email(s) and keeps the old address active
until the link is clicked. The endpoint answers `202` with
`PlayerConfirmationResponse` ("Check your new inbox to confirm the change.")
and does **not** move scores, boards, usage or sessions yet.

The move happens at the next sign-in: Supabase is the source of truth for the
address. The gateway records the address its local data is keyed under in
`app_metadata.profile_email` (admin-only, users cannot write it). When
`verify()` returns a user whose confirmed `email` differs from
`app_metadata.profile_email`, the gateway moves scores, boards, usage and
sessions from the old address to the new one (the existing `move_email` /
`rename_scores_email`), then sets `app_metadata.profile_email` to the new
address. There is no local (non-Supabase) mode any more (spec 0046).

Production Supabase must have **Confirm email** and **Secure email change**
enabled; this is documented. `supabase/config.toml` keeps
`enable_confirmations = false` for local development.

## Acceptance criteria

- **API-SPEND-001**: Given no player session cookie, when `POST /game/run` targets a level whose agent is not `None`, then the answer is `401`, the fake agent records no call, and no usage row is written.
- **API-SPEND-002**: Given an unknown or expired session token, when `POST /game/run` targets a level with an agent, then the answer is `401` and the fake agent records no call.
- **API-SPEND-003**: Given no session cookie, when `POST /game/run` targets an Easy level (agent `None`) with a board of model-free nodes only, then the answer is `200` (classification-only runs stay free and sessionless).
- **API-SPEND-004**: Given a signed-in free player with 0 wave runs used, when they run an Easy level whose board contains a `safety_check` node, then the run succeeds and `wave_runs_used` becomes `1`; given their wave quota is exhausted, the same run answers `429` and the fake check model records no call.
- **API-SPEND-007**: Given an anonymous model run that fails with `503` (agent unavailable), then the session's usage counter does not increment.
- **API-SPEND-009**: Given a `GameRunRequest` whose `custom_message` is 1001 characters, when it is posted, then the answer is `422` and no model is called; given exactly 1000 characters, the request is accepted. Replaced by API-FAIR-002 (0050).
- **API-SPEND-010**: Given a board with 61 nodes (or 201 edges), when it is posted to `/game/run` for any level including `custom`, then the answer is `422` with "A board holds at most 60 nodes and 200 wires." and no model is called.
- **API-SPEND-011**: Given a paid player in custom mode with a board containing `safety_check` and `llm_review`, when the wave runs, then the check nodes are served by the BYOK model built by `byok_factory` and the container's server `game_agent` fake records zero calls.
- **API-SPEND-012**: Given `ALLOW_SELF_UPGRADE` is unset (default `False`), when a signed-in free player calls `POST /auth/upgrade`, then the answer is `403` with "Paid plans are not available yet." and `GET /auth/session` still reports `tier="free"`.
- **API-SPEND-013**: Given `ALLOW_SELF_UPGRADE=True`, when a signed-in free player calls `POST /auth/upgrade`, then the answer is `200` with `tier="paid"`; an anonymous session still gets `403`.
- **API-SPEND-014**: Given `GET /game/levels`, then the response has `self_upgrade_enabled` equal to the `ALLOW_SELF_UPGRADE` setting.
- **API-SPEND-015**: Given a signed-in player, when they `POST /game/scores` with any body, then the answer is `405` and no score is stored; `GET /game/scores` and admin `DELETE /game/scores` behave as before.
- **API-SPEND-016**: Given the generated OpenAPI contract, then `/api/v1/game/scores` has no `post` operation, `GameRunRequest.custom_message` has `maxLength: 1000`, and `GameCatalogResponse` has `self_upgrade_enabled`.
- **API-SPEND-017**: Given a Supabase identity (fake client), when a player changes their email with the correct password, then the gateway calls the user-session `update_user` with `{"email": new}`, never calls `admin.update_user_by_id` with `email_confirm`, answers `202`, and scores, boards and the session still belong to the old address.
- **API-SPEND-018**: Given a Supabase user whose confirmed `email` is `new@x` and whose `app_metadata.profile_email` is `old@x`, when they sign in, then scores, boards and usage keyed `old@x` move to `new@x`, `app_metadata.profile_email` is updated to `new@x` via the admin API, and the session reports `email="new@x"`.
- **API-SPEND-019**: Given a Supabase user whose `user_metadata` (user-writable) names another player's email and whose `app_metadata.profile_email` is unset, when they sign in, then no data is moved and `app_metadata.profile_email` is set to their own email.
- **WEB-SPEND-001**: Given `planCards(session, { selfUpgradeEnabled: false })` for a signed-in free player, then the Paid card's button is disabled with the label "Coming soon"; with `selfUpgradeEnabled: true` it is the existing upgrade action.
- **WEB-SPEND-002**: Given `useShieldApi()`, then it exposes no `submitScore` and no source file under `apps/web/app` posts to `/game/scores`.
- **WEB-SPEND-003**: Given the account email form receives a `202` confirmation response, then the settings page shows "Check your new inbox to confirm the change." and the displayed email stays the old one.
- **API-SPEND-021**: Given no session cookie, when `POST /game/run` targets an Easy level (agent `None`) with a board containing a `jev` node, then the answer is `401` and the fake Jev client records no call; given a signed-in free player, the same run succeeds and `wave_runs_used` increments by 1.
- **API-SPEND-022**: Given an anonymous session, when it runs an Easy level with a `jev` node, then the run is counted against the anonymous session's daily quota (`429` once it is used up, with no Jev call).
- **WEB-SPEND-004**: Given the game client's run call (fake API) answers `401` once, when the player starts a run, then the client calls `signInAnonymously` once and retries the run once; given the retry also answers `401`, then no third attempt is made and the toast shows the gateway's `detail`.
- **API-SPEND-023**: Given a player (or anonymous session) with `N` remaining daily wave or test runs, when `M > N` concurrent `POST /game/run` model-run requests arrive simultaneously, then at most `N` reserve a slot and invoke the server model, `M - N` fail with `429` before calling any model, and `wave_runs_used` (or `test_runs_used`) equals the daily limit on both `InMemoryPlayerStore` and `SupabasePlayerStore` (via atomic Postgres RPC `players.reserve_daily_usage`).
- **API-SPEND-024**: Given a reserved daily wave or test run slot on `InMemoryPlayerStore` or `SupabasePlayerStore`, when `POST /game/run` fails before completion with `422` (`BoardValidationError`) or `502`/`503` (`AgentUnavailableError`), then the reserved slot is released (`players.release_daily_usage`) so the failed run does not reduce remaining daily quota.

## Security & privacy considerations

- All new checks fail closed: an unknown session or a store error refuses the model run.
- `app_metadata` is writable only with the service key; `user_metadata` is never
  trusted for ownership (AGENTS.md rule).
- BYOK keys still never reach logs or saves.
- Removing `POST /game/scores` is a contract change: run `mise run contract`.

## Evaluation impact

None on detection. No scoring change.

## Test changes

Allowed by the user (2026-11-23). No test that covers behaviour which still
exists is weakened.

### Setup edits (behaviour unchanged)

- Harnesses that need a paid player via `POST /auth/upgrade` build `Settings`
  with `ALLOW_SELF_UPGRADE=True`:
  `test_account_settings.py::test_reset_progress_removes_scores_and_boards_only` (API-ACCOUNT-006),
  `test_campaign_api.py::test_catalog_exposes_23_levels_and_enforces_pro_tier_gating` (API-CAMP-001),
  `test_game_agent_api.py::test_daily_limits_are_one_five_and_three_hundred_waves_by_tier` (API-AGENT-001),
  `test_game_api.py::test_player_auth_tiers_ai_node_gate_leaderboard_recording_and_daily_quotas` (API-GAME-007),
  `test_game_levels_api.py::test_settings_pick_a_model_per_tier_and_runs_use_their_own_tier` (API-LEVEL-002),
  `test_player_confirmation.py::test_first_login_creates_a_free_profile_and_keeps_existing_ones` (API-VERIFY-004),
  and the paid-player setup in `test_game_saves_api.py` and `test_game_custom_api.py`.
- Score seeding through `POST /game/scores` is replaced by
  `await container.scores.record_score(ScoreCreateRequest(...), email=...)`:
  the `record_score(client, ...)` helper in `test_account_settings.py` (used by
  API-ACCOUNT tests), `test_game_api.py::test_persist_and_list_scores_ordered_by_rank`
  (API-GAME-004, still checks listing order) and
  `test_game_api.py::test_delete_scores_requires_admin_clearance` (API-GAME-005,
  still checks the admin gate on `DELETE`).
- Model-run tests that post `/game/run` without a cookie on a level with an
  agent first create an anonymous session.

### Tests removed (dead)

| Test / assertion | Reason |
| --- | --- |
| `test_game_api.py::test_player_auth_tiers_ai_node_gate_leaderboard_recording_and_daily_quotas`: the "Anonymous user cannot manually submit scores" block (`POST /game/scores` → `403`) | The endpoint is deleted; API-SPEND-015 asserts `405` for everyone instead. The rest of the test stays. |
| Any other assertion found during implementation whose only subject is `POST /game/scores` or `submitScore` | Same: covers deleted code only. Each is listed here when removed. |

API-GAME-007 (spec 0016, Implemented) was reworded (user approved, 2026-11-23):
its `POST /game/scores` clause is dropped and it points here; its status and
Verification section are unchanged.

## Decisions (resolved 2026-11-23)

- Model run with no session: `401`, then the client creates an anonymous
  session and retries once (WEB-SPEND-004).
- `jev` nodes are model runs (API-SPEND-021/022).
- Anonymous abuse: Vercel BotID plus rate limits (spec 0043), no per-IP daily cap.
- `POST /game/scores` is removed entirely, and `submitScore` with it.
- Test setup edits and dead-test removal as listed above.

## Open questions

None. Resolved 2026-11-23: anonymous cookie cycling is handled by spec 0043
(30 anonymous sessions per IP per hour plus Vercel BotID); the per-IP daily
run cap was dropped. API-SPEND-005, 006 and 008 are retired (never
implemented); API-SPEND-007 now covers only the session counter.
API-SPEND-020 (local-mode immediate email move) is retired: SQLite and the
local identity path are removed by spec 0046.

## Verification

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-SPEND-001, API-SPEND-002, API-SPEND-003, API-SPEND-004, API-SPEND-007, API-SPEND-009, API-SPEND-010, API-SPEND-011, API-SPEND-012, API-SPEND-013, API-SPEND-014, API-SPEND-015, API-SPEND-016, API-SPEND-017, API-SPEND-018, API-SPEND-019, WEB-SPEND-001, WEB-SPEND-002, WEB-SPEND-003, API-SPEND-021, API-SPEND-022, WEB-SPEND-004
- Red: 22 failing test(s) before implementation (`apps/api/tests/test_run_spend_and_integrity.py`, `apps/api/tests/test_run_spend_and_integrity.py`, `apps/api/tests/test_run_spend_and_integrity.py`)
- Green: 22 passing test(s)
- Gate: `mise run check` passed

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-SPEND-023, API-SPEND-024
- Red: 2 failing test(s) before implementation (`apps/api/tests/test_run_spend_and_integrity.py::test_concurrent_model_runs_cannot_exceed_daily_limit_on_memory_or_supabase`, `apps/api/tests/test_run_spend_and_integrity.py::test_failed_model_run_releases_reserved_slot_on_memory_and_supabase`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
