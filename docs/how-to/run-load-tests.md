# Run load tests

This guide tells you how to run the k6 load tests (spec 0057) against the gateway on your
computer.

## Before you start

- Run `mise install`. It installs the pinned k6 version.
- The tests send traffic only to loopback addresses (`localhost`, `127.0.0.1`, `[::1]`).
  To test another host, you must set `K6_ALLOW_REMOTE=1`. Do this only for a host that
  you own and that is not production.

## Start a gateway to test

The safe target is the gateway with in-memory stores. It uses no Supabase, no model and
no payment provider:

```bash
mise run perf:serve
```

For the production rules (rate limits, the proxy secret and BotID), start it in
production mode with a secret of your choice:

```bash
MODE=prod SHIELD_K6_PROXY_SECRET=your-local-secret mise run perf:serve
```

You can also test the local development stack (`mise run dev`) on port 8000.

## Run a scenario

| Task | What it does |
| --- | --- |
| `mise run perf:smoke` | Two VUs call every main route for 20 seconds |
| `mise run perf:load` | The real-play mix at a ramping arrival rate |
| `mise run perf:spike` | 120 readers at once on the leaderboard |
| `mise run perf:stress` | Bursts on the rate-limited routes |
| `mise run perf:soak` | Steady load for `K6_SOAK_DURATION` (default `10m`) |
| `mise run perf:check` | Checks that every scenario is valid (`k6 inspect`) |

For `perf:stress`, use the production-mode gateway and give k6 the same secret:

```bash
K6_PROXY_SECRET=your-local-secret mise run perf:stress
```

## Settings

| Variable | Default | Use |
| --- | --- | --- |
| `K6_TARGET_URL` | `http://127.0.0.1:8000` | The origin to test |
| `K6_ALLOW_REMOTE` | unset | Set to `1` to allow a host that is not loopback |
| `K6_PROXY_SECRET` | unset | Sent as `x-shield-proxy-secret`; never written to a report |
| `K6_REPORT_DIR` | `perf/k6/.reports` | Where the JSON summary goes |
| `K6_SMOKE_DURATION`, `K6_SPIKE_DURATION`, `K6_STRESS_DURATION`, `K6_SOAK_DURATION` | see the scenarios | Run lengths |

## Read the results

Each run writes `perf/k6/.reports/<profile>-summary.json`. The file holds only check names
and aggregate numbers: no request, header, cookie or token. A run fails when one of these
service level objectives fails:

| Metric | Limit |
| --- | --- |
| Failed reads | less than 0.5% |
| Failed writes (not `stress`) | less than 1% |
| Unexpected 5xx responses | 0 |
| `health` latency | p95 less than 50 ms |
| `leaderboard` latency | p95 less than 200 ms, p99 less than 500 ms |
| `game_run` latency (model-free) | p95 less than 600 ms, p99 less than 1,200 ms |
| Checks that pass | more than 99% |

In `stress`, a `429` with `Retry-After` is an expected answer, not a failure.

The `Load` workflow (`.github/workflows/load.yml`) runs the smoke test on demand and every
Monday, and keeps the summary as an artifact for 14 days.
