# Architecture

## Five deployables

`ai-shield` has five separately deployable parts in one repository:

| Part | Role | Talks to |
| --- | --- | --- |
| `packages/engine` (`shield-engine`) | The game's check library: board interpreter, check nodes, levels, the AI agent, the custom sandbox and scoring, plus the bundled baseline classifier | Nothing directly; everything external comes in through ports |
| `apps/api` (`shield-api`) | Gateway (`api.ai-shield.my`): puts the game on HTTP, owns players, quotas, saved boards, the leaderboard, payments and admin clearance, and wires the model providers | Engine (in-process), Gemini, Groq, TypeSafe, the player's BYOK provider, Supabase, Redis, Stripe |
| `apps/web` (`@ai-shield/web`) | Game client (`play.ai-shield.my`): main menu (`/`), defence board (`/game`), plans, and player settings | The gateway only, over the published HTTP contract |
| `apps/admin` (`@ai-shield/admin`) | Isolated admin console (`admin.ai-shield.my`): score statistics, scoreboard reset, and clearance settings | The gateway only, with its dedicated admin proxy secret |
| `apps/landing` (`@ai-shield/landing`) | Static marketing, bilingual legal hub, and client changelog (`ai-shield.my`) | Static content only |

The engine stays free of FastAPI, database drivers and environment variables, so
its rules and scoring are tested in isolation and the gateway can change
without touching them ([ADR 0002](decisions/0002-engine-gateway-split.md)). The
repository keeps the three together so one change can span all of them with one
review and one CI run ([ADR 0001](decisions/0001-monorepo-with-uv-and-bun-workspaces.md)).

## Ports and adapters in the engine

`shield_engine.game` knows only the interfaces in
[`ports.py`](../../packages/engine/src/shield_engine/ports.py):

```
                ┌──────────────────────── shield_engine ────────────────────────┐
 board ───────▶ │ run_wave / evaluate_message                                    │
 level_id ────▶ │   ├── check nodes (word filter, length limit, secret scan …)   │
                │   ├── Jev ──▶ JevClient port                                   │
                │   ├── ML filter (player-trained scikit-learn model)            │
                │   └── final node ──▶ UsageChatModel port ─────────────────────┼──▶ Gemini / Groq / BYOK adapter
 WaveResult ◀── │ score_traces ──▶ WaveScore                                     │
                └────────────────────────────────────────────────────────────────┘
```

The ports are structural `Protocol`s: any object with the right method
satisfies them. Consequences:

- The engine's required dependencies are scikit-learn and joblib. Provider SDKs
  are optional extras (`shield-engine[groq]`) imported only from `adapters/`.
- Test doubles are trivial. `shield_engine.testing` ships deterministic ones
  (`StaticClassifier`, `ScriptedUsageChatModel`) so hosts test with no network.
- Without any model the agent levels still run, on a deterministic offline
  stand-in.

Every prompt the agent reads goes through `wrap_untrusted()`
([`untrusted.py`](../../packages/engine/src/shield_engine/untrusted.py)), so
attacker text arrives as delimited data, never as instructions.

## The composition root

`build_container()` in [`container.py`](../../apps/api/src/shield_api/container.py)
is the only place that reads provider settings. It builds:

- the baseline classifier via `load_baseline()` (hash-verified artifacts)
- the agent model per tier: `standard` on Gemini with `GOOGLE_API_KEY` (else Groq), `budget` on Groq with `GROQ_API_KEY`
- the BYOK factory for the custom sandbox (fixed provider allowlist, no URL field)
- `StripePayments` with `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` (else billing is off)
- the Redis leaderboard, rate limiter, auth flows and trained models with `REDIS_URL` (required in production)
- `SupabaseScoreStore`, `SupabaseSessionStore` and `SupabasePlayerStore` backed by Supabase (`SUPABASE_URL` + `SUPABASE_KEY` are required)

The `Container` is stored on `app.state` and injected into routes through
`ContainerDep`. Tests build a `Container` from fakes and pass it to
`create_app(container)`, so no test patches module globals.

## Inside the gateway

| Layer | Modules | Rule |
| --- | --- | --- |
| Routers | `routers/health.py`, `auth.py`, `account.py`, `billing.py`, `game.py`, `clearance.py` | HTTP mapping only |
| Services | `services/players.py`, `scores.py`, `leaderboard.py`, `sessions.py`, `clearance.py`, `identity.py`, `auth_flows.py`, `admins.py`, `rate_limit.py`, `models.py`, `train_worker.py`, `billing.py`, `passes.py` | Accounts and quotas, the leaderboard, admin sessions, email links, rate limits, trained models, payments, persistence |
| Providers | `providers/gemini.py`, `byok.py`, `typesafe.py` | Model adapters behind `UsageChatModel` and `JevClient` |
| Contract | `schemas.py` | Pydantic models exported to `contracts/shield-api.openapi.json` |

Credentials stop at the gateway. An admin's email and password are checked
once against Supabase Auth at `POST /api/v1/clearance` (the account needs
`app_metadata.role = "admin"`) and exchanged for an `HttpOnly` cookie stored
only as a SHA-256 hash;
a player's BYOK key is used for one custom run and never stored, logged or
echoed.

## Life of a wave run

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (/game)
    participant R as game router
    participant P as Player store
    participant E as Engine (run_wave)
    participant M as Agent model
    participant S as Score store

    B->>R: POST /api/v1/game/run {level_id, board} + player cookie
    R->>P: check_run (quota by tier; Easy and Custom cost nothing)
    R->>E: run_wave(board, level_id, classifier, agents)
    loop each prompt in the level wave
        E->>E: route through the wired checks
        opt prompt reaches the final node on an agent level
            E->>M: objective, tools, player rules, canary, wrap_untrusted(prompt)
            M-->>E: reply + tool calls (judged: leaked / protected / helped)
        end
    end
    E-->>R: traces + WaveScore
    R->>P: consume_run
    opt signed in and agent ran live
        R->>S: record_score (best per player and level)
    end
    R-->>B: GameRunResponse
```

The browser animates the returned traces and shows the score; it computes
nothing that counts.

## Life of a payment

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (/plans)
    participant G as billing router
    participant D as Pass desk
    participant S as Stripe
    participant P as Player store

    B->>G: POST /billing/checkout + player cookie
    G->>D: start (one open checkout for each player)
    D->>P: create_purchase (pending)
    D->>S: create Checkout Session (server price, expires in about 30 minutes)
    G-->>B: Stripe page URL
    B->>S: pay
    S->>G: signed webhook
    G->>D: handle event
    D->>P: fulfil_purchase (row lock, one time)
    B->>G: POST /billing/sync (on return to /plans)
    G->>S: read the session, if the purchase is still pending
```

The webhook grants the pass without the browser. `sync` repairs a missed webhook. The browser never
sends a price and never grants a pass. Details: [Accept payments](../how-to/accept-payments.md).

## Inside the web client

The browser talks only to the gateway
([ADR 0004](decisions/0004-frontend-talks-only-to-gateway.md)). All calls go
through [`useShieldApi()`](../../apps/web/app/composables/useShieldApi.ts), and
all shapes come from `app/types/api.gen.ts`, generated from the committed
OpenAPI contract. Board logic worth testing (graph building, traces, scoring
display, saves, plans, console stats) lives as pure functions in
[`gameBoard.ts`](../../apps/web/app/utils/gameBoard.ts) and
[`customSandbox.ts`](../../apps/web/app/utils/customSandbox.ts).

The first server render uses `shield_session_hint`, a display-only cookie with the player name, tier and
feature flags. `GET /auth/session` corrects it in the background. The gateway ignores the cookie.
The own leaderboard row shows the player name first, then the rank from the gateway. The server render
also loads the leaderboard rows and the billing state from the gateway. It waits 800 ms at most, then the browser loads them.

## Related

- [Threat model](threat-model.md)
- [Repository layout](../reference/repository-layout.md) for the dependency rules
- [HTTP API reference](../reference/http-api.md) for exact shapes
