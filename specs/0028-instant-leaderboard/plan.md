# 0028 — Instant leaderboard: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

### 1. Backend: `RedisCachedScoreStore` + Event Broadcaster (`apps/api`)
- Wrap `SupabaseScoreStore` / `SqliteScoreStore` in `container.py` with a `RedisCachedScoreStore` decorator implementing the existing `ScoreStore` `Protocol` (`apps/api/src/shield_api/services/scores.py`).
- **Redis key layout** (per `SCORE_VERSION = 2`):
  - `leaderboard:v2:z:{level_id}` — `ZSET` mapping `score_id -> composite_score` where `composite_score = total_score + (1.0 - min(avg_latency_ms, 999_999.0) / 1_000_000.0)`.
  - `leaderboard:v2:records` — `HASH` mapping `score_id -> ScoreRecord.model_dump_json()`.
  - `leaderboard:v2:owners:{level_id}` — `HASH` mapping `owner_key -> score_id` (for O(1) old-score cleanup when an owner beats their personal best or deletes their account).
  - Read path fetches `limit + 20` candidates via `ZREVRANGE` + `HMGET` in one pipeline and applies Python's exact `_rank` tie-breaker (`-total_score, avg_latency_ms, total_cost_usd, created_at`) before slicing `[:limit]`.
- **Live event broadcasting**:
  - Introduce a lightweight `LeaderboardNotifier` (`RedisPubSubNotifier` when Redis is enabled, `InMemoryNotifier` otherwise) publishing `{"level_id": ..., "reason": ...}` on `record_score`, `clear_scores`, `delete_scores_for`, and `rename_scores_email`.
  - Expose `GET /api/v1/game/scores/stream` in `apps/api/src/shield_api/routers/game.py` returning a `StreamingResponse(..., media_type="text/event-stream")` with keepalive heartbeats.
- **Configuration, `mise` Dev Workflow & Docker**:
  - Add `REDIS_URL: SecretStr | None = None` to `apps/api/src/shield_api/settings.py` and document `# REDIS_URL=redis://localhost:6379/0` in `apps/api/.env.example` and `docs/reference/configuration.md`.
  - **`mise run dev` stays zero-setup** (matching `db:start` / SQLite): `mise run dev` runs `api:dev` + `web:dev` without requiring Docker or a local Redis daemon. When `REDIS_URL` is unset or Redis is not running, the gateway logs a warning and falls back to the underlying `ScoreStore` + in-process `InMemoryNotifier` for SSE.
  - **Opt-in local Redis (`mise.toml`)**: Mirror `db:start` / `db:stop` with `redis:start` (`docker compose up -d redis`) and `redis:stop` (`docker compose stop redis`) for local testing against real Redis (`REDIS_URL=redis://localhost:6379/0` in `apps/api/.env`).
  - **Full stack (`mise run up`)**: Add a `redis:7-alpine` service with a healthcheck to `compose.yaml` and pass `REDIS_URL=${REDIS_URL:-redis://redis:6379/0}` to the `api` service so containerized runs have Redis enabled automatically.

### 2. Frontend: `useLeaderboard()` Composable with `useState` + SSE (`apps/web`)
- Create `apps/web/app/composables/useLeaderboard.ts` using Nuxt `useState` (matching `usePlayerAuth.ts`, no Pinia):
  - `scores`: `useState<ScoreRecord[]>('shield_leaderboard_scores', () => [])`
  - `hasLoaded`: `useState<boolean>('shield_leaderboard_loaded', () => false)`
  - `loading`: `useState<boolean>('shield_leaderboard_loading', () => false)`
  - `selectedTab`: `useState<LevelId>('shield_leaderboard_tab', () => 'easy')`
- Add `refreshScores({ background?: boolean })`:
  - When `background` is `true` (or `hasLoaded.value` is `true`), do not clear `scores` and do not show a loading empty state.
  - Deduplicate concurrent in-flight requests so rapid SSE bursts or double-mounts issue at most one fetch.
- Add `connectStream()` / `disconnectStream()` using browser `EventSource` against `${apiBaseUrl}/api/v1/game/scores/stream`, debounced (300ms) on `leaderboard` events.
- Update:
  - `apps/web/app/pages/index.vue`: run `refreshSession()` and `refreshScores({ background: hasLoaded.value })` in parallel via `Promise.all`; connect SSE stream on mount and disconnect on unmount; guard `<UEmpty>` with `hasLoaded && !loading && filteredScores.length === 0`.
  - `apps/web/app/pages/game.vue`: call `refreshScores({ background: true })` after a recordable live wave run succeeds.
  - `apps/web/app/pages/settings.vue`: call `refreshScores({ background: true })` after resetting progress or deleting the account.

## Interfaces

```python
# apps/api/src/shield_api/services/scores.py
class LeaderboardNotifier(Protocol):
    async def publish(self, *, level_id: str | None, reason: str) -> None: ...
    def subscribe(self) -> AsyncIterator[dict[str, str | None]]: ...

class RedisCachedScoreStore:
    def __init__(
        self,
        inner: ScoreStore,
        redis_client: Any,
        notifier: LeaderboardNotifier | None = None,
    ) -> None: ...
```

```typescript
// apps/web/app/composables/useLeaderboard.ts
export const useLeaderboard = () => {
  // returns { scores, hasLoaded, loading, selectedTab, refreshScores, connectStream, disconnectStream }
}
```

```text
GET /api/v1/game/scores/stream -> text/event-stream
  event: leaderboard
  data: {"level_id": "easy", "reason": "recorded"}
```

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract (plus SSE stream URL)
- [ ] New configuration (`REDIS_URL`) is documented in `docs/reference/configuration.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Pinia (`@pinia/nuxt`) | User requested `useState` instead of Pinia; `usePlayerAuth.ts` already uses `useState`, avoiding an extra frontend dependency. |
| Polling `GET /api/v1/game/scores` every N seconds | Wastes requests when idle and adds up to N seconds of lag; SSE + Redis Pub/Sub pushes updates immediately only when scores change. |
| Redis-only without Supabase/SQLite | Redis is volatile/in-memory; Supabase/SQLite remains the durable source of truth for `board_json` and cold-start hydration. |

## Risks and rollback

- **Stale cache on out-of-band DB edits**: Mitigated by TTL on Redis keys (e.g., 1 hour) and write-through/invalidation on all API mutations.
- **Redis outage**: Caught per-operation in `RedisCachedScoreStore`, logging a warning and falling back to `inner` (`SupabaseScoreStore` / `SqliteScoreStore`).
- **Rollback**: Unset `REDIS_URL` to disable Redis caching immediately with zero schema changes.
