# 0057 — k6 load testing

- **Status:** Implemented
- **Area:** DEV | API
- **Owner:** Terry Ong
- **Created:** 2026-11-27
- **Related:** [0041-same-origin-api-proxy](../0041-same-origin-api-proxy/spec.md), [0043-rate-limiting-and-client-ip](../0043-rate-limiting-and-client-ip/spec.md), [0044-leaderboard-read-scaling](../0044-leaderboard-read-scaling/spec.md), [0054-backend-security-hardening](../0054-backend-security-hardening/spec.md)

## Problem

`ai-shield` relies on Redis sorted-set caching, fixed-window rate limits, threadpool-dispatched Supabase PostgREST calls (`asyncio.to_thread`), and Nitro reverse-proxying in production, yet has no automated load or performance regression testing:

1. **Cold-cache leaderboard stampedes are untested under concurrency.** Spec 0044 added a single-flight Redis rebuild lock (`_WAIT_FOR_REBUILD_SECONDS = 2.0`), but there is no spike test proving concurrent `GET /api/v1/game/leaderboard` requests stay fast without overloading `SupabaseScoreStore`.
2. **Threadpool and connection saturation are unmeasured.** FastAPI wraps synchronous `supabase-py` calls in `asyncio.to_thread()` while running rate limits, session lookups, saved-board reads, and deterministic game runs. Concurrency bottlenecks or connection leaks are invisible until production.
3. **Rate-limit saturation behaviour is unverified at scale.** Under burst traffic (`429 Too Many Requests` with `Retry-After`), gateway latency, error accounting, and Redis failover need load verification.
4. **Unsafe ad-hoc scripts risk hitting production or burning paid LLM/Stripe quotas.** Running load scripts without host allowlists or deterministic model-free boards could flood production, trigger Vercel WAF/BotID lockouts, or consume real Gemini/Groq API budgets.

## Goals

- Provide a modular Grafana **k6** load-testing suite under `perf/k6/` covering five distinct performance profiles: `smoke`, `load`, `spike`, `stress`, and `soak`.
- Enforce strict safety guardrails so k6 refuses non-local target URLs by default and uses only model-free deterministic levels (`easy-1`, `easy-2`) and synthetic test accounts (never live LLM nodes or Stripe Checkout).
- Define clear quantitative SLO thresholds (`p95`, `p99`, error rate excluding expected `429` in stress profiles) per endpoint class.
- Integrate a fast, deterministic `mise run perf:smoke` check locally and an on-demand/scheduled `.github/workflows/load.yml` workflow for full profiles with downloadable summary reports.

## Non-goals

- Load-testing third-party external APIs (Supabase Cloud, Stripe Checkout, Gemini, Groq, OpenAI) or bypassing production Vercel BotID/WAF.
- Running multi-minute `stress` or `soak` tests on every pull request in `ci.yml` (kept fast via `smoke`, with heavier profiles manual/scheduled).
- Changing `packages/engine` scoring or classifier behaviour.

## Behaviour

### 1. Target safety guardrails

- Every k6 entrypoint reads `K6_TARGET_URL` (default `http://127.0.0.1:8000` for direct gateway runs or `http://127.0.0.1:3000` for Nitro proxy runs).
- In `setup()`, if `K6_TARGET_URL` is not loopback (`localhost`, `127.0.0.1`, `[::1]`) and `K6_ALLOW_REMOTE` is not `"1"`, k6 aborts immediately with a non-zero exit code.
- If `K6_PROXY_SECRET` is provided (for staging/production-mode proxy verification), it is read from the environment, attached only as `x-shield-proxy-secret`, and never written to stdout, logs, or summary files.
- Wave-run payloads use only deterministic, model-free campaign boards (`easy-1` / `easy-2` with `word_filter`, `length_limit`, `text_cleanup`) so zero external LLM calls occur.

### 2. Test suite structure (`perf/k6/`)

| File | Purpose |
| --- | --- |
| `lib/config.js` | Target URL resolution, loopback safety guard, SLO threshold presets, optional proxy header builder. |
| `lib/boards.js` | Deterministic `easy-1` / `easy-2` board payloads and synthetic `.invalid` test-user builders. |
| `lib/checks.js` | Reusable `check()` assertions, custom `Trend`/`Rate`/`Counter` metrics (`shield_leaderboard_duration`, `shield_wave_run_duration`, `shield_unexpected_5xx`), and redacted `handleSummary` exporter. |
| `scenarios/smoke.js` | 1–2 VUs for 20s verifying `/health`, `/game/levels`, `/game/leaderboard`, `/auth/anonymous`, `/game/progress`, and model-free `/game/run`. |
| `scenarios/load.js` | Ramping arrival-rate mix reflecting real player traffic (70% leaderboard/catalog reads, 20% anonymous session + progress/save reads, 10% model-free `POST /game/run`). |
| `scenarios/spike.js` | Sudden burst (`0 -> 100+` concurrent readers) on `GET /api/v1/game/leaderboard` (optionally after cache flush in local dev) validating single-flight rebuild and sub-second `p95`. |
| `scenarios/stress.js` | Burst `POST /api/v1/auth/anonymous`, `POST /api/v1/game/run`, and `POST /api/v1/auth/login` against rate-limited routes; uses `http.setResponseCallback` so expected `429` responses with `Retry-After` are tracked separately from `5xx` failures. |
| `scenarios/soak.js` | Sustained moderate load (default 10m, configurable via `K6_SOAK_DURATION`) checking memory stability, threadpool responsiveness, and zero latency drift. |

### 3. SLO thresholds

| Profile / Metric | Threshold |
| --- | --- |
| `http_req_failed{kind:read}` | `< 0.5%` |
| `http_req_failed{kind:write}` (non-stress) | `< 1.0%` |
| `shield_unexpected_5xx` (all profiles, including `stress`) | `== 0` |
| `http_req_duration{endpoint:health}` | `p(95) < 50ms` |
| `http_req_duration{endpoint:leaderboard}` | `p(95) < 200ms`, `p(99) < 500ms` |
| `http_req_duration{endpoint:game_run}` (model-free) | `p(95) < 600ms`, `p(99) < 1200ms` |
| `checks` pass rate | `> 99%` |

### 4. Reporting, tooling, and CI

- `handleSummary()` outputs a concise terminal summary and writes JSON metrics to `perf/k6/.reports/<profile>-summary.json` (git-ignored), omitting all cookies, tokens, and secret headers.
- `mise.toml` exposes `perf:smoke`, `perf:load`, `perf:spike`, `perf:stress`, `perf:soak`, and `perf:check` (validating k6 script syntax/linting via `k6 inspect` or ESLint).
- `k6` tool version is pinned in `mise.toml` (or validated via `mise` / official Grafana k6 GitHub Action in `.github/workflows/load.yml`).
- `.github/workflows/load.yml` runs `smoke` on `workflow_dispatch` (and optional nightly schedule) against an isolated local/ephemeral API + Redis stack and uploads the redacted JSON summary artifact.

## Acceptance criteria

- **DEV-LOAD-001**: Given `perf/k6/lib/config.js` receives `K6_TARGET_URL=https://example.com` without `K6_ALLOW_REMOTE=1`, when any k6 scenario runs `setup()`, then it aborts immediately with a non-zero exit code before sending load traffic.
- **DEV-LOAD-002**: Given all k6 scenarios in `perf/k6/scenarios/`, when inspected or executed, then every `POST /api/v1/game/run` payload uses deterministic model-free nodes (`word_filter`, `length_limit`, `text_cleanup`) and never transmits external LLM provider keys or Stripe Checkout requests.
- **DEV-LOAD-003**: Given a running `apps/api` instance (with Redis and local Supabase or memory fallback), when `mise run perf:smoke` executes `perf/k6/scenarios/smoke.js`, then all `health`, `levels`, `leaderboard`, `anonymous`, `progress`, and `game/run` checks pass and all SLO thresholds stay green.
- **DEV-LOAD-004**: Given `perf/k6/scenarios/spike.js`, when concurrent VUs burst against `GET /api/v1/game/leaderboard` across `Easy`, `Medium`, `Hard`, and `All`, then `p(95)` stays under 200ms, `p(99)` stays under 500ms, and `shield_unexpected_5xx` equals `0`.
- **DEV-LOAD-005**: Given `perf/k6/scenarios/stress.js` running against an API with production-style rate limits enabled, when requests exceed fixed-window limits and receive `429` with `Retry-After`, then `http.setResponseCallback` classifies `429` as expected rate-limit rejections, `shield_unexpected_5xx` stays `0`, and `health` latency remains below threshold.
- **DEV-LOAD-006**: Given `handleSummary` in `perf/k6/lib/checks.js`, when a run finishes and writes `perf/k6/.reports/<profile>-summary.json`, then the summary file contains aggregated latency/error metrics and contains zero session cookies, `x-shield-proxy-secret` values, or raw tokens.
- **DEV-LOAD-007**: Given `mise.toml` and `.github/workflows/load.yml`, then `mise run perf:check` validates all k6 scenario files cleanly, and `.github/workflows/load.yml` passes `actionlint` and `zizmor` with pinned action SHAs.

## Security & privacy considerations

- **No production accidents:** Loopback enforcement prevents accidental DDoS of production Vercel deployments from developer machines.
- **No secret leakage:** Proxy bypass secrets (`K6_PROXY_SECRET`) and test cookies exist only in process memory during the k6 run and are stripped from reports and stdout.
- **Cost protection:** Blocking paid LLM nodes and billing endpoints in load scenarios guarantees zero surprise OpenAI/Gemini/Groq/Stripe charges.

## Evaluation impact

None. No change to `packages/engine` scoring or classifiers.

## Open questions

None.

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: DEV-LOAD-001, DEV-LOAD-002, DEV-LOAD-003, DEV-LOAD-004, DEV-LOAD-005, DEV-LOAD-006, DEV-LOAD-007
- Red: 8 failing test(s) before implementation (`scripts/tests/test_load_tests.py::test_remote_targets_need_an_explicit_opt_in`, `scripts/tests/test_load_tests.py::test_k6_aborts_before_sending_load_to_a_remote_target`, `scripts/tests/test_load_tests.py::test_payloads_are_model_free_and_send_no_provider_keys`)
- Green: 8 passing test(s)
- Gate: `mise run check` passed
