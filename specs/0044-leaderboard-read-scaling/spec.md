# 0044 — Leaderboard on Redis sorted sets

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-23
- **Related:** [0028-instant-leaderboard](../0028-instant-leaderboard/spec.md) (superseded by this spec), [0046](../0046-remove-sqlite-supabase-only/spec.md) (Supabase-only store), [0039-campaign-levels-and-difficulty-leaderboard](../0039-campaign-levels-and-difficulty-leaderboard/spec.md), [0041-same-origin-api-proxy](../0041-same-origin-api-proxy/spec.md) (WEB-PROXY-002), [0043](../0043-rate-limiting-and-client-ip/spec.md) (production configuration guard)

## Problem

Production is Vercel (the gateway runs as serverless functions), Supabase
(Postgres via PostgREST) and Upstash Redis (redis-py via `REDIS_URL`). Local
development uses the local Supabase stack (spec 0046 removes SQLite). Today:

1. **Every read aggregates everything.** `GET /game/leaderboard` calls
   `scores.list_all_current_scores()` and `aggregate_difficulty_leaderboard` in
   Python on every request (`routers/game.py`, `services/scores.py`).
   `RedisCachedScoreStore` caches the raw rows in one `owned` hash but still
   decodes and aggregates all of them per request, so cost grows with the number
   of players.
2. **Silent truncation.** `SupabaseScoreStore.list_all_current_scores` has no
   `.range()`; PostgREST returns at most 1000 rows by default.
3. **SSE does not fit serverless.** `GET /game/scores/stream` holds a function
   open per viewer (billed for its whole life and cut at the platform's max
   duration), and each event makes every client refetch all three tabs at once.
4. **No CDN caching** of the public leaderboard.
5. **Dead weight.** Per-level ZSETs, a records hash, the `owned` hash,
   hydration locks and `warm_cache` exist to serve paths that this design
   replaces.

## Goals

- A leaderboard read costs O(log P + N) Redis work (P players, N rows), not O(P).
- Supabase `game.scores` stays the source of truth; Redis is a derived index
  that can be rebuilt at any time.
- Writes update the index incrementally, atomically, only when a best row changes.
- No long-lived connections: clients poll; a CDN absorbs anonymous reads.
- Remove the structures, routes and client code this replaces.

## Non-goals

- Changing ranking rules, `_replaces`, scoring or `SCORE_VERSION`.
- Changing the `DifficultyLeaderboardEntry` response shape.
- Moving aggregation into SQL / materialised views.
- Per-level leaderboards for players (no client uses them; see `GET /game/scores` below).

## Behaviour

### Source of truth (unchanged)

`game.scores` keeps one best row per owner per level under the existing
`_replaces` rules (a won run beats a lost one; then rank by score, latency,
cost; `won` and `mastered` are sticky). `record_score` now also returns a
`ScoreChange(previous: ScoreRecord | None, current: ScoreRecord | None,
changed: bool)` describing the stored best before and after the write.

### Redis index (one per difficulty)

Boards: `Easy`, `Medium`, `Hard` and `All` (the API still serves
`difficulty=None`). Keys use the prefix `lb:v<SCORE_VERSION>:`, so a version
bump starts a fresh index.

| Key | Type | Content |
| --- | --- | --- |
| `lb:v<ver>:z:<board>` | ZSET | member → primary score |
| `lb:v<ver>:d:<board>` | HASH | fields `<member>:name`, `<member>:name_at`, `<member>:total`, `<member>:mastered`, `<member>:solved`, `<member>:lat_milli`, `<member>:cost_nano` |
| `lb:v<ver>:ready:<board>` | STRING | `1` once the board is built (an empty ZSET does not exist in Redis, so this marks "built, possibly empty") |
| `lb:v<ver>:lock:<board>` | STRING | rebuild lock (`SET NX PX 30000`) |
| `lb:v<ver>:dirty:<board>` | STRING | set by writes that land while a rebuild holds the lock |

- **Member** = SHA-256 hex of the existing `_owner_key(player_name, email)`
  (`email:<addr>` or `anon:<name>`). Emails never appear in keys, members or
  values.
- **Contributions.** Only won rows count (today's `rec.won` filter). Per owner
  per board: `total` = Σ total_score, `mastered` = Σ mastered, `solved` = number
  of won levels, `lat_milli` = Σ round(avg_latency_ms × 1000), `cost_nano` =
  Σ round(total_cost_usd × 10⁹), `name` = player_name of the most recently
  created best row (`name_at` = its `created_at`).
- **Primary score** = `total × 32 + mastered` (exact integer; mastered ≤ 23 < 32,
  total ≤ 23 × 10,000, so the value stays far below 2⁵³).

**Why not one float.** Today's order is `(-total_score, -levels_mastered,
avg_latency_ms, total_cost_usd, player_name)`. Latency and cost are unbounded
reals; packing all of them into one IEEE double cannot keep exact order. So the
ZSET orders by the first two keys exactly, and the rest is a deterministic
tie-break on read.

### Read: `GET /game/leaderboard?difficulty=X&limit=N`

1. If `ready:<board>` is missing, rebuild (below).
2. `ZREVRANGEBYSCORE z +inf 32 WITHSCORES LIMIT 0 N` (min 32 ⇔ `total ≥ 1`,
   matching today's `total_score > 0` filter). Let `s` be the N-th score.
3. If N rows came back, `ZRANGEBYSCORE z s s LIMIT 0 250` fetches the tie group
   at the boundary (members above `s` are all already included; capped at 250 so
   pathological ties stay bounded).
4. One `HMGET` of the display fields for the fetched members.
5. Compute `avg_latency_ms = round(lat_milli / 1000 / solved, 2)` and
   `total_cost_usd = round(cost_nano / 10⁹, 6)`, sort by the full key above,
   return the first N.

Cost: O(log P + N + T) where T is the tie group at the boundary. Response shape
is unchanged. The Python fallback (`aggregate_difficulty_leaderboard`) switches
to the same fixed-point sums so both paths produce identical output.

### "My rank": `GET /game/leaderboard/me?difficulty=X`

Signed-in (non-anonymous) players only (`403` otherwise). Response
`LeaderboardRankResponse { difficulty, rank: int | null, total_score: int | null }`.
`rank` = 1 + `ZCOUNT z (s +inf` + the number of members in the player's tie
group (`ZRANGEBYSCORE z s s LIMIT offset 250` + `HMGET`, scanning up to
1,000 tied members and scaling via `ZCOUNT` if more than 1,000 tie) that sort
before them by the full key; each member is paired with its own decoded hash
record before filtering incomplete records (and if the caller's own hash record
is missing while their ZSET score exists, `ready:<board>` is deleted and the
store fallback answers);
`null` when the player has no won level on that board. Header
`Cache-Control: private, no-store`.

### Write: recorded score

When `/game/run` records a score and `ScoreChange.changed` is true, the gateway
runs **one Lua script** (`EVALSHA`, atomic in Redis/Upstash) per affected board
(the level's difficulty and `All`):

- subtract the previous best's contribution if it was won, add the new best's
  if it is won (`ZINCRBY` by Δ primary, `HINCRBY` on the counters, `HSET`
  name/name_at when the new row is newer);
- if `solved` reaches 0, `ZREM` the member and `HDEL` its fields.

Lost runs, and runs that do not change the stored best, touch nothing. No full
recount. The script runs only if `ready:<board>` exists; if a rebuild holds
`lock:<board>`, the write sets `dirty:<board>` instead (the rebuild picks it up).

### Rebuild

Triggered by a read or write that finds `ready:<board>` missing (Upstash wiped,
or a new `SCORE_VERSION` prefix):

1. `SET lock:<board> <token> NX PX 30000`. Only the holder rebuilds.
2. Read current rows from the store with paginated `.range(offset, offset+999)`
   ordered by `id` until a short page (summary columns only, no
   `board_json`), compute contributions, write them to
   temporary keys, then `RENAME` temp → live and `SET ready:<board>`, all in
   one `MULTI`.
3. If `dirty:<board>` was set during the rebuild, delete it and `ready:<board>`
   so the next request rebuilds again. Release the lock only if it still holds
   our token (compare-and-delete script).
4. Instances that do not get the lock poll `ready:<board>` for up to 2 s, then
   answer from the store with the Python aggregation (paginated read + 10 s
   in-process cache).

### Other mutations

| Mutation | Redis update |
| --- | --- |
| Admin clear (`DELETE /game/scores`) | `DEL` every `lb:v<ver>:*` key of the four boards, then `SET ready:<board>` (built and empty) |
| Account delete / reset progress (`delete_scores_for(email)`) | Lua per board: `ZREM` the member, `HDEL` its fields |
| Email rename (`rename_scores_email(old, new)`) | Lua per board: move score and fields from `member(old)` to `member(new)`; if `member(new)` already exists, delete `ready:<board>` (rebuild) |

### Redis unavailable, or not configured

Any Redis error on read: log a warning, answer from the store with the Python
aggregation (paginated) plus a 10 s in-process cache. Write-side Redis errors
are logged and delete nothing in the store; they mark the board for rebuild on
the next successful Redis call (best effort: `DEL ready:<board>`). Local
development without `REDIS_URL` always uses the store path (local Supabase).
Production requires `REDIS_URL` and Supabase (spec 0043, API-PROD-*).

### `GET /game/scores` (per-level raw list)

Still used by the admin console (`pages/console/index.vue`, `getScores(undefined, 100)`).
Kept as a minimal path read straight from the store (no Redis structure), with
no CDN header. `useLeaderboard().refreshRawScores` and its `scores` state are
unused and removed.

### Removed

- `RedisCachedScoreStore` with its per-level ZSETs, records hash, `owned` hash
  (`leaderboard:v*:owned`), hydration locks and `warm_cache` (and the warm-up
  task in `main.py`).
- `GET /game/scores/stream`, `LeaderboardNotifier`, `InMemoryNotifier`,
  `RedisPubSubNotifier`, `container.leaderboard_notifier` and every `publish` call.
- Web: the `EventSource`, `LEADERBOARD_STREAM_PATH`, and the proxy route's
  event-stream flush branch (the generic streaming in `proxyToGateway`,
  WEB-PROXY-013, stays).

### HTTP caching

`GET /game/leaderboard`: `Cache-Control: public, s-maxage=10, stale-while-revalidate=30`
(user-confirmed: CDN on top of Upstash). `GET /game/leaderboard/me`:
`private, no-store`. `GET /game/scores` and `GET /game/progress`: no `public`.

### Web client (`useLeaderboard`)

- Polls the **active** difficulty tab every 20 s while the home page is mounted
  and `document.hidden` is false; polling pauses while hidden, and on becoming
  visible it refetches at once if the last fetch is older than 20 s.
- Refetches the active tab immediately after the player's own run records a
  score, and after resetting progress.
- Other tabs are fetched when switched to, if their data is older than 20 s.
- Keeps the `useState` + `sessionStorage` instant paint (no empty-state flash).

### Web: the player's own row (mobile-game style)

The top-25 list renders as today. For the active difficulty tab the client
also loads `/game/leaderboard/me` (signed-in players only) with the same polling
and post-run refetch, and decides with a pure function
`ownRowPlacement(entries, me, session)` in `app/utils/`:

| Situation | Result |
| --- | --- |
| Anonymous or signed out | `none`: no pinned row, no highlight |
| Signed in, ranked, rank ≤ rows shown | `highlight`: one own row, in the list. It sticks to the bottom edge of the list while its place is below the visible rows. When the player scrolls to its place, it stays between the players above and below it |
| Signed in, ranked, rank > rows shown | `pin`: the last row of the list, which always sticks to the bottom edge, and shows rank, name and total score |
| Signed in, unranked (`rank: null`) | `pin`: the same row shows `#-`, the player name and a total score of 0 |
| Signed in, rank not loaded | The same row shows the player name, with `#-` for the rank and `-` for the score (WEB-LBOARD-019) |

Rank labels come from a pure `formatRankLabel(rank)`: exact below 1,000
(`"#999"`), compact above (`"1K+"` for 1,000–1,999, `"2K+"`, …, `"10K+"`).
The pinned row follows the active tab and refreshes with it.

### Contract changes (`mise run contract`)

- Removed: `GET /api/v1/game/scores/stream`.
- Added: `GET /api/v1/game/leaderboard/me` and `LeaderboardRankResponse { difficulty, rank, total_score }`.
- Unchanged shapes: `/game/leaderboard`, `/game/scores`.

## Acceptance criteria

### Index and reads

- **API-LBOARD-011**: Given seeded random data (≥ 1,000 owners, many equal `total_score` and `levels_mastered` values, random latencies and costs) loaded into a fake async Redis through the write path, when `GET /game/leaderboard` is read for each board and limits 1, 10, 25 and 100, then the rows equal `aggregate_difficulty_leaderboard` over the same store rows exactly (same order and same field values).
- **API-LBOARD-012**: Given a board with 5,000 owners in the fake Redis, when the leaderboard is read with `limit=25`, then the store is not read and the Redis commands issued are one `ZREVRANGEBYSCORE`, at most one `ZRANGEBYSCORE` and one `HMGET` (command count independent of the number of owners).
- **API-LBOARD-013**: Given members whose primary scores tie at the N-th position, when the leaderboard is read with `limit=N`, then the boundary tie group is fetched and ordered by `avg_latency_ms`, `total_cost_usd`, `player_name`, matching the Python aggregation. Replaced by API-FAIR-005 (0050).
- **API-LBOARD-014**: Given any stored score, then no Redis key, ZSET member or hash field/value contains the owner's email (members are SHA-256 of `_owner_key`).
- **API-LBOARD-015**: Given an owner whose only rows are lost runs, or whose total is 0, then they are not listed (min primary score 32).
- **API-LBOARD-032**: Given more than 250 players tied at the boundary primary score on a Redis leaderboard board, when `get_leaderboard(limit=25)` or `get_player_rank` resolves ties, then `ZRANGEBYSCORE` is invoked with `start=0, num=250` and `HMGET` fetches at most `limit + 250` entries (`250` for `get_player_rank`).
- **API-LBOARD-033**: Given tied players on a Redis board where an earlier tied member's hash fields are incomplete, when `get_player_rank` runs, then remaining tied players stay paired with their own decoded records and return their exact rank and `total_score`; if the caller's own hash record is incomplete while their ZSET score exists, `ready:<board>` is deleted and the store fallback returns their exact rank.
- **API-LBOARD-034**: Given 400 players tied at the same primary score on a Redis board where the caller has the slowest latency (rank 400), when `get_player_rank` runs, then `ZRANGEBYSCORE` and `HMGET` execute in bounded chunks (`<= 250` members per call) and return exact `rank == 400` (never understated at `<= 250`).

### Writes

- **API-LBOARD-016**: Given a player's won best on `easy-1` of 6,000, when they record a won 7,000 on `easy-1`, then `Easy` and `All` each get exactly one script call and the owner's `total` rises by 1,000 and `solved` stays the same; the next read reflects it without any store read.
- **API-LBOARD-017**: Given a stored won best, when the player records a lower or lost run that does not replace it (`ScoreChange.changed` false), then no Redis write happens.
- **API-LBOARD-018**: Given a won best that is not mastered, when a run of equal or higher rank flips `mastered` to true, then `mastered` rises by 1 on both boards and the primary score rises by 1.
- **API-LBOARD-019**: Given a script that fails midway (fake Redis raising inside the script), then neither the ZSET nor the hash is changed (atomic), the store write still succeeds, a warning is logged, and `ready:<board>` is deleted so the next read rebuilds.
- **API-LBOARD-020**: Given an admin clear, then all four boards read empty immediately and are marked ready (no rebuild on the next read).
- **API-LBOARD-021**: Given a player with rows on two boards, when `delete_scores_for` (account delete or reset progress) runs, then their member and fields are gone from every board and other players are unchanged.
- **API-LBOARD-022**: Given an email rename, then the old member is gone, the new member has the same score and fields, and the next read lists the player once.

### Rebuild

- **API-LBOARD-023**: Given the store holds rows but Redis has no `ready:<board>`, when the leaderboard is read, then the board is rebuilt from the store, the answer equals the Python aggregation, and `ready:<board>` is set.
- **API-LBOARD-024**: Given two `Container`s sharing a fake Redis and both reading a missing board at once, then exactly one rebuilds (one store scan), and the other answers correct rows (from waiting or from the store path).
- **API-LBOARD-025**: Given a write that lands while another instance holds `lock:<board>`, then `dirty:<board>` is set, and after the rebuild finishes the board is rebuilt again on the next read, so the write is reflected.
- **API-LBOARD-026**: Given a bumped `SCORE_VERSION`, then reads use the new `lb:v<ver>:` prefix and trigger a rebuild; old-prefix keys are ignored.
- **API-LBOARD-009**: Given a fake Supabase client holding 2,500 current score rows that returns at most 1000 rows per request and honours `.range()`, when `list_all_current_scores` runs, then it returns all 2,500 rows and issued 3 ranged requests.

### Fallback and caching

- **API-LBOARD-027**: Given a Redis client that raises on every command, when the leaderboard is read twice within 10 s, then both answers equal the Python aggregation, the store is read once (10 s in-process cache), and a warning is logged; after 10 s (fake clock) the store is read again.
- **API-LBOARD-028**: Given no `REDIS_URL` (development, fake Supabase client), then the leaderboard is served by the paginated store path with the 10 s cache.
- **API-LBOARD-010**: Given `GET /game/leaderboard`, then the response has `Cache-Control: public, s-maxage=10, stale-while-revalidate=30`; `GET /game/scores` and `GET /game/progress` carry no `public` `Cache-Control`.

### My rank

- **API-LBOARD-029**: Given a signed-in player ranked 3rd on `Easy` (with a tie on primary score resolved by latency), when they call `GET /game/leaderboard/me?difficulty=Easy`, then the answer is `{difficulty: "Easy", rank: 3, total_score: …}` with `Cache-Control: private, no-store`; with no won `Easy` level, `rank` and `total_score` are `null`; anonymous or no session gets `403`. Replaced by API-FAIR-005 (0050).

### Removed structures and routes

- **API-LBOARD-030**: Given the app, then `GET /api/v1/game/scores/stream` answers `404`, the contract has no such path, and `shield_api` defines no `LeaderboardNotifier`, `InMemoryNotifier`, `RedisPubSubNotifier`, `RedisCachedScoreStore` or `warm_cache`.
- **API-LBOARD-031**: Given `GET /game/scores?limit=100` (admin console), then it answers from the store as before (same records and order) with no Redis access.

### Web

- **WEB-LBOARD-005**: Given the home page with fake timers and a fake `getLeaderboard`, when 60 s pass while visible, then the active tab is fetched 3 times and the other tabs not at all.
- **WEB-LBOARD-006**: Given `document.hidden` becomes true, then no fetch happens while hidden; when it becomes visible after more than 20 s, the active tab is fetched once immediately.
- **WEB-LBOARD-007**: Given the player's own run records a score (or they reset progress), then the active tab is refetched immediately, without waiting for the next poll.
- **WEB-LBOARD-008**: Given a tab whose data is older than 20 s, when the user switches to it, then it is fetched once; switching to a tab fetched less than 20 s ago makes no request.
- **WEB-LBOARD-009**: Given leaderboard data in `sessionStorage`, when the home page mounts, then the cached rows render on the first frame with no "No scores yet" flash.
- **WEB-LBOARD-011**: Given `formatRankLabel`, then `1` → `"#1"`, `999` → `"#999"`, `1000` → `"1K+"`, `1999` → `"1K+"`, `2500` → `"2K+"`, `10000` → `"10K+"`.
- **WEB-LBOARD-012**: Given `ownRowPlacement` with the 25 shown entries, then: anonymous or signed out → `none`; signed in with `rank` 7 → `highlight` (row 7); `rank` 40 → `pin` with label `"#40"`; `rank: null` → `pin` with label `"#-"` and score 0; own rank not loaded yet → `none`.
- **WEB-LBOARD-013**: Given the leaderboard and a signed-in player, when it renders, then the player has exactly one row. With `highlight`, it is the list row, highlighted and sticky to the bottom edge of the scroll area until the player scrolls to its place. In all other cases it is a row after the list, sticky to the same edge. The own row has the inverted background (white in dark mode, black in light mode) and no border. The table itself is the only scroll area, and its header row stays at the top while the list scrolls.
- **WEB-LBOARD-014**: Given a signed-in player with no rank (also with no plays), then the own row shows `#-`, the player name and a total score of 0.
- **WEB-LBOARD-015**: Given a signed-in player, when the active tab changes, after each 20 s poll, and right after their own run records a score, then `/game/leaderboard/me` is fetched for the active difficulty only; for anonymous players it is never fetched.
- **WEB-LBOARD-016**: Given the leaderboard table, then the rank is its own column before `Player`, player names align with the `Player` header, and the pinned row uses the same alignment.
- **WEB-LBOARD-017**: Given a difficulty with no scores, then the leaderboard table stays visible with its column headers and shows `No scores yet` in the `UTable` empty state (no `UEmpty`); before the first load it does not show `No scores yet`. A signed-in player sees their own row instead of the empty state, also during the first load.
- **WEB-LBOARD-018**: Given a page load of `/`, then the server render contains the active leaderboard rows; if the gateway does not answer in 800 ms, the page renders without them and the browser loads them.
- **WEB-LBOARD-019**: Given a signed-in player, when the page is refreshed, then the first server render has the pinned row with the display name, `#-` for the rank and `-` for the score. When the rank loads, the same row shows the real values. Sign-out or a change of player clears the rank. The row has no skeleton.
- **WEB-LBOARD-020**: Given a refresh, then the rows and the own rank load in parallel, and a session that is confirmed after the first load triggers the rank load immediately, not at the next poll.
- **WEB-LBOARD-021**: Given the Vercel projects, then the web and gateway functions run in `sin1`, the same region as Redis and the nearest to the players and Supabase (Tokyo).
- **WEB-LBOARD-010**: Given the web sources, then nothing under `apps/web/app` or `apps/web/shared` creates an `EventSource` or references `/game/scores/stream` or `LEADERBOARD_STREAM_PATH`, and `useLeaderboard` exposes no `refreshRawScores`.

### Retired IDs

| ID | Reason |
| --- | --- |
| API-LBOARD-001 to 007 | Replaced the "cache the aggregated list, invalidate on write" design with incremental ZSETs (API-LBOARD-011 to 028). |
| WEB-LBOARD-001 to 004 | Assumed SSE events with jittered refetch; SSE is removed in favour of polling (WEB-LBOARD-005 to 008). |
| WEB-LBOARD-022 | Skeleton rows; removed at the owner's request, the empty state of WEB-LBOARD-017 stays. |
| API-LBOARD-008 | SQLite removed by 0046 (the Supabase path reads summary columns only, covered by API-LBOARD-009). |

## Test changes

Removed as dead (they test code this spec deletes):

| Test | Reason |
| --- | --- |
| `apps/api/tests/test_redis_leaderboard.py::test_warm_redis_cache_returns_exact_ranked_order_without_hitting_inner_store` (API-SCORE-001) | Per-level Redis cache removed. |
| `…::test_cold_redis_cache_hydrates_from_inner_store_on_first_read` (API-SCORE-002) | Per-level hydration removed. |
| `…::test_record_score_on_cold_redis_does_not_mask_existing_inner_scores` (API-SCORE-002) | Same. |
| `…::test_mutations_invalidate_redis_and_publish_sse_notifications` (API-SCORE-003) | Notifier and SSE removed. |
| `…::test_sse_stream_survives_keepalive_timeout_without_stop_async_iteration` (API-SCORE-003) | SSE route removed. |
| `…::test_list_scores_all_levels_hydrates_in_single_inner_query` (API-SCORE-001/002) | Per-level hydration removed. |
| `…::test_list_all_current_scores_caches_in_redis_with_singleflight_and_write_through` (API-SCORE-001/002/003) | `owned` hash removed. |
| `apps/web/test/instantLeaderboard.test.ts` `[WEB-SCORE-003]` EventSource test | EventSource removed. |

Rewritten (behaviour still exists):

- `test_redis_leaderboard.py::test_gateway_falls_back_to_inner_score_store_when_redis_is_unset_or_unreachable` (API-SCORE-004) → targets the new store-path fallback (covered by API-LBOARD-027/028).
- `instantLeaderboard.test.ts` `[WEB-SCORE-001]` tests → drop the `getScores` expectation; keep the useState / sessionStorage / active-tab-first assertions.
- `test_contract.py` route list: drop `/api/v1/game/scores/stream`, add `/api/v1/game/leaderboard/me`.
- `apps/web/test/apiProxy.test.ts` `[WEB-PROXY-002]` → asserts the reworded invariant (`useLeaderboard` reads only through `useShieldApi()`, no stream path); same ID.
- Kept unchanged: `test_supabase_summary_queries_fall_back_when_mastery_columns_missing` (API-CAMP-003), WEB-PROXY-013.

## Security & privacy considerations

- Emails never enter Redis: members are hashes of the owner key; display data
  holds only player name and numbers.
- Redis is a derived index; losing or corrupting it costs a rebuild, never data.
- Public CDN caching only on `/game/leaderboard`, which reads no cookies;
  `/me` is `private, no-store`.
- Rebuild is single-flight across instances with an expiring lock and a
  compare-and-delete release, so a crashed holder cannot block rebuilds for
  more than 30 s.
- Removing SSE removes long-lived unauthenticated connections.

## Evaluation impact

None. Ranking and scoring are unchanged; API-LBOARD-011 proves output equality.

## Open questions

None. Resolved 2026-11-24: "my rank" is included (API-LBOARD-029, WEB-LBOARD-011
to 015); spec 0028 is `Superseded by 0044`; spec 0041 WEB-PROXY-002 is reworded
to a stable invariant (same ID); one full rebuild after a failed Redis write is
accepted; CDN caching on `/game/leaderboard` is kept on top of Upstash.

## Verification

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-LBOARD-011, API-LBOARD-012, API-LBOARD-013, API-LBOARD-014, API-LBOARD-015, API-LBOARD-016, API-LBOARD-017, API-LBOARD-018, API-LBOARD-019, API-LBOARD-020, API-LBOARD-021, API-LBOARD-022, API-LBOARD-023, API-LBOARD-024, API-LBOARD-025, API-LBOARD-026, API-LBOARD-009, API-LBOARD-027, API-LBOARD-028, API-LBOARD-010, API-LBOARD-029, API-LBOARD-030, API-LBOARD-031, WEB-LBOARD-005, WEB-LBOARD-006, WEB-LBOARD-007, WEB-LBOARD-008, WEB-LBOARD-009, WEB-LBOARD-011, WEB-LBOARD-012, WEB-LBOARD-013, WEB-LBOARD-014, WEB-LBOARD-015, WEB-LBOARD-010
- Red: 34 failing test(s) before implementation (`apps/api/tests/test_leaderboard_scaling.py`, `apps/api/tests/test_leaderboard_scaling.py`, `apps/api/tests/test_leaderboard_scaling.py`)
- Green: 34 passing test(s)
- Gate: `mise run check` passed

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-LBOARD-032
- Red: 1 failing test(s) before implementation (`apps/api/tests/test_leaderboard_scaling.py::test_massive_tie_at_cutoff_caps_zrangebyscore_and_hmget_reads`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-LBOARD-033, API-LBOARD-034
- Red: 2 failing test(s) before implementation (`apps/api/tests/test_leaderboard_scaling.py::test_get_player_rank_pairs_members_accurately_when_hash_record_incomplete`, `apps/api/tests/test_leaderboard_scaling.py::test_massive_tie_at_cutoff_caps_zrangebyscore_and_hmget_reads`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: WEB-LBOARD-016
- Red: 1 failing test(s) before implementation (`leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-016] index.vue puts the rank in its own column before the player name`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: WEB-LBOARD-012, WEB-LBOARD-014
- Red: 2 failing test(s) before implementation (`leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-012] ownRowPlacement chooses none, highlight, or pin`, `leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-014] index.vue renders pinned row outside table and highlights in-list row`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 42212fc (+ uncommitted changes)

- Criteria: WEB-LBOARD-017
- Red: 1 failing test(s) before implementation (`leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-017] index.vue keeps the table and uses its own empty state`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-LBOARD-018, WEB-LBOARD-019, WEB-LBOARD-020, WEB-LBOARD-021
- Red: 4 failing test(s) before implementation (`instant first render (spec 0044) [WEB-LBOARD-018] loads the rows in the server render with a time limit`, `instant first render (spec 0044) [WEB-LBOARD-019] restores the own row from a hint of the same player only`, `instant first render (spec 0044) [WEB-LBOARD-020] loads the rank in parallel and as soon as the session is confirmed`)
- Green: 4 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-LBOARD-018
- Red: 2 failing test(s) before implementation (`instant first render (spec 0044) [WEB-LBOARD-018] loads the rows in the server render with a time limit`, `instant first render (spec 0044) [WEB-LBOARD-018] stops waiting for a gateway that does not answer`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-LBOARD-022
- Red: 1 failing test(s) before implementation (`instant first render (spec 0044) [WEB-LBOARD-022] shows skeleton rows for a difficulty that has not loaded`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-LBOARD-013, WEB-LBOARD-019
- Red: 3 failing test(s) before implementation (`instant first render (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-019] pins the display name first and fills in the rank when it loads`, `leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-014] index.vue renders pinned row outside table and highlights in-list row`, `instant first render (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-019] pins the display name first and fills in the rank when it loads`)
- Green: 3 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-LBOARD-013
- Red: 1 failing test(s) before implementation (`leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-014] index.vue shows one own row that sticks to the bottom edge until its place in the list`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-LBOARD-013
- Red: 1 failing test(s) before implementation (`leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-014] index.vue shows one own row that sticks to the bottom edge until its place in the list`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed

### 2026-11-25 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-LBOARD-012, WEB-LBOARD-013, WEB-LBOARD-014, WEB-LBOARD-017, WEB-LBOARD-019
- Red: 9 failing test(s) before implementation (`leaderboard read scaling & my rank (spec 0044) [WEB-LBOARD-012] ownRowPlacement chooses none, highlight, or pin`, `instant first render (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-019] pins the display name first and fills in the rank when it loads`, `instant first render (spec 0044) [WEB-LBOARD-013] [WEB-LBOARD-014] [WEB-LBOARD-017] [WEB-LBOARD-019] gives a signed-in player exactly one row, in every state`)
- Green: 10 passing test(s)
- Gate: `mise run check` passed
