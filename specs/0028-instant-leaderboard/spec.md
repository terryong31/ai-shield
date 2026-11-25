# 0028 — Instant leaderboard

- **Status:** Superseded by 0044
- **Note:** Surviving behaviours carried into [0044](../0044-leaderboard-read-scaling/spec.md): WEB-SCORE-002 → WEB-LBOARD-007 (refetch after the player's own run or reset); WEB-SCORE-001 → WEB-LBOARD-009 (instant paint, no empty-state flash).
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-15
- **Related:** [0016-game-engine](../0016-game-engine/spec.md), [0021-game-level-tiers](../0021-game-level-tiers/spec.md), [0025-account-settings](../0025-account-settings/spec.md)

## Problem

1. **Slow backend reads:** `GET /api/v1/game/scores` queries Supabase/PostgREST synchronously inside a worker thread on every request, sorting across four columns and transferring full `board_json` payloads.
2. **Flash of empty leaderboard on navigation:** In `apps/web/app/pages/index.vue`, `scores` is stored in a local component `ref([])`. Navigating to `/settings` (or `/game`, `/plans`) and returning to `/` unmounts and remounts the page, resetting `scores` to `[]` and flashing `"No scores yet"` (`UEmpty`) until `refreshSession()` and `getScores()` resolve sequentially.
3. **No live updates:** When a player achieves a new leaderboard score in `/game` or resets progress in `/settings`, or when another player records a score, `/` has no mechanism to update immediately or receive live leaderboard changes without a manual reload or re-navigation.

## Goals

- Serve `GET /api/v1/game/scores` in sub-millisecond time from a Redis Sorted Set (`ZSET`) + Hash cache while keeping Supabase/SQLite as the durable source of truth.
- Keep leaderboard state in Nuxt's built-in `useState` (`useLeaderboard()` composable, no Pinia) so navigating between `/`, `/settings`, `/game`, and `/plans` renders cached scores on frame 1 with zero empty-state flash.
- Propagate leaderboard changes immediately — both locally after score/reset mutations and across active viewers via Server-Sent Events (SSE) backed by Redis Pub/Sub (with an in-process fallback when Redis is not configured).

## Non-goals

- Changing the `ScoreRecord` ranking formula (`total_score DESC`, `avg_latency_ms ASC`, `total_cost_usd ASC`, `created_at ASC`) or `SCORE_VERSION`.
- Adding Pinia (`@pinia/nuxt`) to `apps/web`.
- Replacing Supabase/SQLite as the source of truth for `board_json` or historical persistence.

## Behaviour

### Backend (`apps/api`)

| Operation | Behaviour |
| --- | --- |
| `GET /api/v1/game/scores` | Reads top `limit` scores from Redis `ZSET` + `HASH` in a single pipeline on cache hit. On cache miss (cold Redis), reads from the underlying `ScoreStore` (`SupabaseScoreStore` / `SqliteScoreStore`), hydrates Redis, and returns. |
| `POST /api/v1/game/run` / `POST /api/v1/game/scores` | Writes to the underlying `ScoreStore` first (write-through), updates Redis `ZSET` + `HASH` (removing any superseded score for the same owner/level), and publishes a `leaderboard` update event. |
| `DELETE /api/v1/game/scores` / account reset / email rename | Updates/invalidates affected Redis keys and publishes a `leaderboard` update event so deleted or renamed scores never linger in cache. |
| `GET /api/v1/game/scores/stream` | Streams `text/event-stream` (`SSE`) notifications (`event: leaderboard`, JSON `{ "level_id": "<id\|null>", "reason": "recorded\|cleared\|deleted" }`) whenever the leaderboard changes. |
| `REDIS_URL` unset or Redis unreachable | Logs a warning and degrades gracefully to the underlying `ScoreStore` and an in-process `asyncio` broadcaster for SSE. |

### Frontend (`apps/web`)

- `useLeaderboard()` stores `scores`, `hasLoaded`, `loading`, and `selectedTab` in Nuxt `useState` keys so state survives route changes.
- On `/` mount:
  - `refreshSession()` and `refreshScores({ background: hasLoaded.value })` run in parallel (`Promise.all`).
  - Cached `scores` render immediately; `<UEmpty title="No scores yet" />` is shown **only** when `hasLoaded && !loading && filteredScores.length === 0`.
- Live updates:
  - `/game` triggers `refreshScores({ background: true })` (or `invalidate()`) immediately after a recordable live wave run completes.
  - `/settings` triggers `refreshScores({ background: true })` after resetting progress or deleting the account.
  - `/` subscribes to `GET /api/v1/game/scores/stream` via `EventSource` while mounted and visible, debouncing incoming events into a background refresh.

## Acceptance criteria

- **API-SCORE-001**: Given `REDIS_URL` is configured and Redis is warm, when `GET /api/v1/game/scores` is called, then scores are returned from Redis in exact `(total_score DESC, avg_latency_ms ASC, total_cost_usd ASC, created_at ASC)` order without querying the underlying `ScoreStore`.
- **API-SCORE-002**: Given Redis is empty (cold cache), when `GET /api/v1/game/scores` is called, then the store reads from the underlying `ScoreStore`, hydrates Redis, and returns the scores; subsequent calls hit Redis.
- **API-SCORE-003**: Given a player records a higher score, clears scores, or resets/deletes their account, when the write completes, then Redis is updated/invalidated immediately and connected `GET /api/v1/game/scores/stream` subscribers receive an SSE `leaderboard` event.
- **API-SCORE-004**: Given `REDIS_URL` is unset or Redis raises a connection error, when `list_scores` or `record_score` is called, then the gateway falls back to the underlying `ScoreStore` without failing the request.
- **WEB-SCORE-001**: Given the leaderboard has already loaded on `/`, when the user navigates to `/settings` and returns to `/`, then the cached scores render immediately without flashing `"No scores yet"` while a background refresh runs.
- **WEB-SCORE-002**: Given a signed-in player completes a recordable live wave on `/game` or resets progress on `/settings`, when the action succeeds, then `useLeaderboard()` refreshes in the background so `/` shows the updated leaderboard immediately.
- **WEB-SCORE-003**: Given the user is on `/` and a `leaderboard` SSE event arrives from `/api/v1/game/scores/stream`, when the debounce window elapses, then `useLeaderboard()` silently refreshes scores without clearing the visible table.

## Security & privacy considerations

- Redis stores only `ScoreRecord` JSON (which never includes `email`, per `scores.py`) and an internal `owner_key` mapping for deduplication; emails are never exposed over `/api/v1/game/scores` or `/api/v1/game/scores/stream`.
- SSE events carry only `{ level_id, reason }` (no player PII or board payloads).
- Redis connection strings (`REDIS_URL`) are `SecretStr` in `Settings` and never logged or sent to the client.

## Evaluation impact

Not applicable (no engine scoring or classifier changes).

## Open questions

- Confirm adding `redis[hiredis]` to `apps/api/pyproject.toml` (per `AGENTS.md` dependency approval rule). Yes confirm. 
- Confirm whether `REDIS_URL` should be enabled by default in `compose.yaml` with a `redis:7-alpine` service. Yes confirm. 

## Verification

### 2026-11-15 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-SCORE-001, API-SCORE-002, API-SCORE-003, API-SCORE-004, WEB-SCORE-001, WEB-SCORE-002, WEB-SCORE-003
- Red: 7 failing test(s) before implementation (`apps/api/tests/test_redis_leaderboard.py`, `apps/api/tests/test_redis_leaderboard.py`, `apps/api/tests/test_redis_leaderboard.py`)
- Green: 7 passing test(s)
- Gate: `mise run check` passed

### 2026-11-15 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-SCORE-003
- Red: 1 failing test(s) before implementation (`apps/api/tests/test_redis_leaderboard.py::test_sse_stream_survives_keepalive_timeout_without_stop_async_iteration`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed

### 2026-11-16 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-SCORE-002, WEB-SCORE-001, WEB-SCORE-003
- Red: 3 failing test(s) before implementation (`apps/api/tests/test_redis_leaderboard.py::test_record_score_on_cold_redis_does_not_mask_existing_inner_scores`, `instant leaderboard (spec 0028) [WEB-SCORE-001] uses Nuxt useState in useLeaderboard, parallelizes index mount, and prevents empty-state flash`, `instant leaderboard (spec 0028) [WEB-SCORE-003] subscribes to /api/v1/game/scores/stream via EventSource and debounces background refreshes`)
- Green: 4 passing test(s)
- Gate: `mise run check` passed

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: WEB-SCORE-001
- Red: 1 failing test(s) before implementation (`instant leaderboard (spec 0028) [WEB-SCORE-001] uses Nuxt useState in useLeaderboard, parallelizes index mount, and prevents empty-state flash`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
