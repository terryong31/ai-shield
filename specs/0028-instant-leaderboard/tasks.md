# 0028 — Instant leaderboard: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0028 API-SCORE-001 API-SCORE-002 API-SCORE-003 API-SCORE-004 WEB-SCORE-001 WEB-SCORE-002 WEB-SCORE-003`
- [ ] **API-SCORE-001**: write failing test (Redis ZSET cache hit + exact rank ordering)
- [x] **API-SCORE-002**: write failing test (cold-cache hydration from inner ScoreStore)
- [x] **API-SCORE-003**: write failing test (write-through, delete/clear invalidation, SSE event publish)
- [ ] **API-SCORE-004**: write failing test (graceful fallback when Redis is unset or unreachable)
- [x] **WEB-SCORE-001**: write failing test (`useLeaderboard` `useState` persistence + no empty-state flash on remount)
- [ ] **WEB-SCORE-002**: write failing test (background refresh triggered from `/game` score record and `/settings` reset)
- [x] **WEB-SCORE-003**: write failing test (SSE `leaderboard` event triggers debounced background refresh)
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Add `redis` service to `compose.yaml`, `redis:start`/`redis:stop` tasks to `mise.toml`, and `REDIS_URL` to `apps/api/.env.example`
- [ ] Update reference docs (`docs/reference/configuration.md`) and `CHANGELOG.md`
- [ ] Regenerate the API contract if HTTP shapes changed (`mise run contract`)
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
