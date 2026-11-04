# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the packages use
[Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- `ai-shield` Defender workflow game (`shield_engine.game`, `/api/v1/game/levels`, `/api/v1/game/train-classifier`, `/api/v1/game/run`, `/api/v1/game/scores`, `/`, `/game`, `/_console`):
  - Game main menu (`/`): Play Game level selector (Easy, Medium, Hard cards with descriptions and high scores), Settings modal (dark/light theme switch and BYOD OpenAI/Groq secret keys), and live Leaderboard per difficulty.
  - Interactive node-based defence board (`/game`): locked anchor nodes (`Input`, `Safe` on Level 1 / `Assistant` on Levels 2–3, and `Blocked`), 9 placeable tool nodes (`Text cleaner`, `Word filter`, `Length limit`, `Secret scanner`, `ML filter`, `Quick screen`, `Safety check`, `Agent review`, `Tool filter`), double-click node configuration modal with custom CSV dataset upload and training (`logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`) and in-game LLM model selection, live message counts on anchor nodes, and quit confirmation modal.
  - Hidden admin console (`/_console`): guarded by `UAuthForm` with clearance session authentication and no client-side references on public pages (spec 0011).
- Clearance sessions: `POST/GET/DELETE /api/v1/clearance` exchange the passphrase once for an `HttpOnly` session cookie; only a SHA-256 hash of the token is stored in SQLite. Failed attempts are rate-limited per address and keep `DENIED` clearance for the window. New settings `SESSION_TTL_MINUTES`, `SESSION_COOKIE_SECURE`, `CLEARANCE_MAX_ATTEMPTS`, `CLEARANCE_WINDOW_MINUTES` (spec 0012).
- Enforced SDD + TDD cycle (`mise run sdd:start|red|green|verify|done`): evidence-checked transitions, `## Verification` records in specs, and Claude Code hooks that lock production code until red is proven, forbid agents from accepting specs, and block stopping mid-cycle (spec 0010).
- SQLite audit log (`SQLITE_PATH`, default `var/shield.db`) used whenever Supabase is not fully configured; `/health` reports `audit_backend` (spec 0009).
- Supabase CLI project in `supabase/` (config, `requests` migration with RLS, local seed) and `mise run db:*` tasks.
- `compose.yaml` running API + web, with the SQLite audit log in a named volume; API image health check.
- Monorepo layout with uv and bun workspaces: `packages/engine`, `apps/api`, `apps/web`.
- `shield-engine`, a framework-free engine: `Shield` pipeline with streaming events, pluggable ports, Groq adapter, public test doubles (`shield_engine.testing`).
- Evaluation harness and `shield-engine eval|train` CLI; held-out seed evaluation set; model card.
- SHA-256 verification of bundled model artifacts before deserialisation.
- Gateway endpoints `POST /api/v1/screen`, `GET /api/v1/requests` and `GET /api/v1/stats`.
- Committed OpenAPI contract with typed `ChatEvent` stream schema; the web client's types are generated from it.
- Specs 0001–0008 with traceable acceptance criteria; CI gates for spec coverage and contract drift.
- Diátaxis documentation, ADRs, AGENTS.md, Claude Code skills, subagents and a formatting hook.
- Dockerfiles for the API and web apps; GitHub Actions CI.

### Changed
- **Breaking:** `ChatRequest` and `ScreenRequest` no longer accept `passphrase`; clearance comes from the session cookie. Audit metadata records `clearance` instead of `passphrase_provided`. CORS now allows credentials and `DELETE`, defaults to local loopback origins (`localhost`, `127.0.0.1`, `[::1]`, `[::]`), and rejects a `*` origin. The web client no longer stores the passphrase in `localStorage` and removes any old copy on load (spec 0012).
- The web client no longer talks to Supabase; all data goes through the gateway.
- The NDJSON stream uses one `\n` per event; `debate_step` was renamed `DEBATE_TURN`; `BLOCK` carries `layer`; `POLICY_UPDATE` carries `allowed_tools`.
- The demo assistant runs only the tools that the decision's policy allows, and passes tool results to the LLM.
- Allowed requests that went through Layer 2 are logged at `LAYER_2_DUAL_AGENT` (previously `SYSTEM`).
- Online learning no longer overwrites the committed model file.

### Removed
- Unprefixed (pre-`/api/v1`) route aliases.
- The legacy Next.js application.

### Security
- The caller's passphrase is no longer interpolated into LLM prompts. The engine receives only a `Clearance` level, and the passphrase is compared in constant time.
- The screened prompt is wrapped as untrusted data in adjudicator prompts, with delimiter look-alikes neutralised.
- `drop_database_table` is rated `CRITICAL` (it was `LOW`, which left it available under `RESTRICTED`).
- `SECURE_PASSPHRASE` has no built-in default.
- Stream errors no longer echo exception text to clients.
