# 0057 — k6 load testing: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Build a self-contained, modular k6 suite under `perf/k6/` with mise tasks and a dedicated GitHub Actions workflow:

1. **Shared library (`perf/k6/lib/`):**
   - `config.js`: Reads `__ENV.K6_TARGET_URL` (default `http://127.0.0.1:8000`), parses hostname, fails `setup()` unless host is `localhost`, `127.0.0.1`, `[::1]`, or `__ENV.K6_ALLOW_REMOTE === '1'`. Supports `K6_API_PREFIX` (`/api/v1`) and optional `K6_PROXY_SECRET` header.
   - `boards.js`: Exports deterministic model-free `easy-1` (`word_filter` + `length_limit`) and `easy-2` (`text_cleanup` + `word_filter`) board payloads matching `GameRunRequest` in `contracts/shield-api.openapi.json`.
   - `checks.js`: Defines custom `Trend` (`shield_leaderboard_duration`, `shield_wave_run_duration`), `Rate` (`shield_unexpected_5xx`, `shield_rate_limited`), and `handleSummary(data)` writing redacted JSON summaries to `perf/k6/.reports/`.
2. **Scenarios (`perf/k6/scenarios/`):**
   - `smoke.js`: Constant 2 VUs, 20s; exercises the full anonymous player loop (`GET /health`, `GET /game/levels`, `GET /game/leaderboard`, `POST /auth/anonymous`, `GET /game/progress`, `POST /game/run`).
   - `load.js`: `ramping-arrival-rate` executor simulating mixed read/write gameplay traffic with tagged requests (`endpoint`, `kind`) so thresholds apply per route class.
   - `spike.js`: `ramping-vus` spike from 5 -> 120 -> 5 VUs over `GET /api/v1/game/leaderboard?difficulty=Easy|Medium|Hard|All` to test Redis ZSET reads and single-flight rebuild stability.
   - `stress.js`: Configured with `http.setResponseCallback(http.expectedStatuses({ min: 200, max: 399 }, 429))` so expected `429` throttling is verified via `check(res, { '429 has Retry-After': ... })` while `shield_unexpected_5xx == 0` stays strict.
   - `soak.js`: Configurable `K6_SOAK_DURATION` (default `10m`) at steady arrival rate to detect memory growth or threadpool exhaustion.
3. **Tooling, verification tests, and CI:**
   - Pin `k6` in `mise.toml` (ask user before adding tool/dependency if needed, or confirm `mise` tool pin), add `perf:smoke`, `perf:load`, `perf:spike`, `perf:stress`, `perf:soak`, and `perf:check` (`k6 inspect` across all scenarios).
   - Add `perf/k6/.reports/` to `.gitignore`.
   - Add Python verification tests (`scripts/tests/test_k6_suite.py` with `@pytest.mark.spec("DEV-LOAD-001")` .. `"DEV-LOAD-007"`) that verify loopback guard behaviour, model-free payloads, summary redaction, and run `k6 inspect` / smoke verification when `k6` is available.
   - Add `.github/workflows/load.yml` (`workflow_dispatch` + weekly schedule) running API + Redis + `mise run perf:smoke` and uploading the JSON summary artifact, verified with `mise run lint:actions` (`actionlint` + `zizmor`).

## Interfaces

No production application HTTP routes, schemas, or `packages/engine` APIs change.

New repo paths:

- `perf/k6/lib/{config,boards,checks}.js`
- `perf/k6/scenarios/{smoke,load,spike,stress,soak}.js`
- `.github/workflows/load.yml`

New `mise.toml` tool & tasks (confirm adding `k6` tool pin before implementation):

- `[tools] k6 = "<pinned version>"`
- `perf:check`, `perf:smoke`, `perf:load`, `perf:spike`, `perf:stress`, `perf:soak`

## Boundaries check

- [x] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [x] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] Load-testing usage and environment variables (`K6_TARGET_URL`, `K6_ALLOW_REMOTE`, `K6_PROXY_SECRET`) are documented in `docs/how-to/` and `docs/reference/`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Locust (Python) instead of k6 | k6 is a single static Go binary with native arrival-rate executors, first-class SLO threshold exit codes, built-in `http.setResponseCallback`, and zero Python GIL overhead on the load generator itself. |
| Running k6 directly against production Vercel | Violates Vercel BotID / WAF protections and risks hitting real LLM/Supabase quotas; staging or local Docker/API+Redis stacks give deterministic, safe benchmarks. |

## Risks and rollback

- **k6 binary availability in CI:** Pinned via `mise` `[tools]` or pinned `grafana/setup-k6-action` SHA in `load.yml`.
- **Rate-limiter interference during `load.js`:** In `APP_ENV=development`, gateway rate limits are off by default so `load.js` measures true backend throughput; `stress.js` targets `APP_ENV=production` (with local Redis + `TRUSTED_PROXY_SECRET`) specifically to exercise rate limiting.
- **Rollback:** Delete `perf/k6/`, `.github/workflows/load.yml`, and the `perf:*` tasks from `mise.toml`.
