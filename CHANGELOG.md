# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the packages use
[Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- Saved boards (spec 0023): signed-in players can `Save` their board for each level and get it back when they open the level again, on any device (`GET`/`PUT /api/v1/game/saves/{level_id}`, stored in `game.saved_boards`). The button shows a dot while there are unsaved changes; anonymous players are asked to sign in. Custom mode also saves the agent, dataset, provider and model, never the API key.
- Custom sandbox for paid players (spec 0022): bring your own agent (objective, tools, rules), dataset (CSV of normal and attack prompts) and model key. One vendor-neutral adapter covers OpenAI, Anthropic, Google, Groq, DeepSeek, Qwen and Kimi through their OpenAI-compatible APIs, with fixed base URLs and no URL field. The key stays in browser memory, is used for one run and is never logged, stored or echoed. Sandbox runs use no quota and are never ranked. `httpx` is now a direct gateway dependency.
- Game AI Agent (spec 0020): every board now ends at one `AI Agent` node that runs a real chat model (first configured of Gemini, then Groq) with the level objective, its allowed and forbidden tools, and up to 5 player-written rules. Leaks are judged from a per-run canary and forbidden tool calls; benign requests must be answered with the right tool. With no model configured a deterministic stand-in runs (`agent_mode: "simulated"`) and scores are not recorded. New `UsageChatModel` port and `ChatCompletion` (token usage) in the engine, implemented by the Groq and Gemini adapters; `ScriptedUsageChatModel` test double.
- New game score: protection 4,000, helpfulness 2,000, tool use 1,000, tokens 1,500, speed 750, cost 750, minus 1,000 per leak. Traces return the agent's reply, tool calls and token counts.
- Redesigned board nodes: labelled input and outputs, `stops here` on unwired outputs, an info button, live in/pass/block counts, run state, animated edges for the path prompts took, and a distinct frame for `Input` and `AI Agent`.
- Client-level player authentication (`/api/v1/auth/session`, `/api/v1/auth/anonymous`, `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/recover`, `/api/v1/auth/upgrade`, `/api/v1/auth/logout`, `usePlayerAuth()`, `enable_anonymous_sign_ins = true` in `supabase/config.toml`) with two user types:
  - Free anonymous users (`is_anonymous=true`): high scores are not recorded or shown on the leaderboard, and AI agent nodes (`safety_check`, `agent_review`) are locked.
  - Logged-in users (`tier="free"` or `"paid"`): high scores are automatically recorded on the leaderboard upon wave completion, AI agent nodes are unlocked, and `free` users receive `3` wave runs and `10` single-message tests per UTC day until upgraded to `paid`.
- `ai-shield` Defender workflow game (`shield_engine.game`, `/api/v1/game/levels`, `/api/v1/game/train`, `/api/v1/game/run`, `/api/v1/game/scores`, `/`, `/game`, `/_console`):
  - Game main menu (`/`): Play Game level selector (Easy, Medium, Hard cards with descriptions and high scores), link to `/settings`, and live Leaderboard per difficulty.
  - Dedicated settings page (`/settings`) with theme selector (`UColorModeSelect`), and player authentication pages (`/auth/login`, `/auth/register`, `/auth/recover`) with `UAuthForm`.
  - Interactive node-based defence board (`/game`): locked anchor nodes (`Input`, `Safe` on Level 1 / `Assistant` on Levels 2–3, and `Blocked`), 9 placeable tool nodes (`Text cleaner`, `Word filter`, `Length limit`, `Secret scanner`, `ML filter`, `Quick screen`, `Safety check`, `Agent review`, `Tool filter`), double-click node configuration modal with custom CSV dataset upload and training (`logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`) and in-game LLM model selection, live message counts on anchor nodes, a fixed-width `Tools` panel laying out tools as a two-column grid of portrait `UCard`s (click or drag onto the canvas, with an info modal per tool), and quit confirmation modal.
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
- Game runs start without a sign-in prompt (WEB-AGENT-015): pressing `Run wave` deducts an attempt at once, and on Medium and Hard the run bar shows `n/N attempts left today` to the right of `Save` (WEB-AGENT-016). The header now shows a large `Results` button and `High Score:`, followed by the high-score wave's stars, which are always shown and survive `Restart` (WEB-AGENT-019) (the best wave on this level this visit, kept across `Restart`) (WEB-AGENT-017). `Run results` now leads with the stars, the total score and a `New record!` badge when the wave beats your high score (WEB-AGENT-018). A `Show breakdown` button opens the score breakdown with average latency, cost and agent tokens. The points list folds into a collapsed `Points` accordion that shows the total (WEB-AGENT-021). The stat tiles have icons, and a zero penalty shows `0` rather than `-0`. The confusion matrix also lives in the breakdown (WEB-AGENT-020) under a `Prompt outcomes` heading, and clicking a matrix cell opens the prompts in that cell. `Run wave` is disabled once no attempts remain. The sign-in prompt now appears only when an anonymous player saves.
- The final node on Medium, Hard and the custom sandbox is now called `Protected Agent` (Easy stays `Help Desk`); its modal says "Wire your last check here. Everything that arrives gets answered, so only let safe prompts through." and the objective is headed `System Instruction`. Board validation now refers to "the final node" (ENG-LEVEL-007, WEB-LEVEL-005).
- Wires now meet the `in` port at its dot like outputs do, and the AI Agent modal says what the node does under its title (WEB-AGENT-013). In every node settings modal, each section's help text is a question-mark tooltip beside the heading; board nodes keep their description line (WEB-AGENT-014).
- The AI Agent modal no longer shows a `Model` section (WEB-LEVEL-004).
- Nodes no longer have a `block` output: a block always stops the prompt at that node, and older `block` wires are ignored (ENG-AGENT-011). Node settings drop the `Outputs` form (wire on the board instead), use number inputs for thresholds and the length limit, and a select menu for the ML filter algorithm. Node ports are larger and centred on the node border (WEB-AGENT-012).
- Level cards on `/` no longer show a model label; the model is named only in the AI Agent modal (WEB-LEVEL-003).
- After each wave a `Run results` modal shows a confusion matrix (normal or injection, got through or stopped) with the prompts in each cell; a `Results` button reopens it. Node settings modals no longer show a `Last wave` section (WEB-AGENT-011).
- Storage is split into domain schemas, with nothing left in `public` (spec 0024): `audit` (`requests`, `clearance_sessions`), `game` (`scores`, `saved_boards`) and `players` (`accounts`, `sessions`, `daily_usage`). With Supabase configured, clearance sessions, players and leaderboard scores now persist in Postgres (scores were previously kept in memory). SQLite mirrors the layout with one attached file per schema beside `SQLITE_PATH`; older single-file databases are not migrated. Every table has RLS on and no `anon` or `authenticated` access.
- Game levels now differ by model (spec 0021). Easy is classification only: it ends at a `Help Desk`, runs no model, scores protection, helpfulness, speed and cost, and never counts toward the daily quota. Medium runs a modern model (`GAME_MODEL_STANDARD`) and Hard a small, low-cost model (`GAME_MODEL_BUDGET`, default `llama-3.1-8b-instant`). The AI Agent modal names the model and level cards say which model each level defends. Leaderboard rows carry `score_version`; only version 2 is listed. The agent reply parser now accepts fenced or chatty JSON.
- Game node modals show latency and cost under the title, drop the `Remove node` button and the `Last run` lists, and show a `Last wave` summary of normal prompts passed and injections stopped. The run bar shows the wave result as 0 to 3 stars (WEB-AGENT-010).
- The `Blocked` and `Safe` anchor nodes are removed; prompts that never reach the AI Agent count as blocked. Boards that still contain a `blocked` node are rejected with `422`.
- Daily run limits: anonymous 1 wave and 3 tests, free 5 waves and 20 tests, paid 300 waves and 1000 tests. Anonymous players are asked to sign in before every run. A run is charged only after it succeeds; a chat model failure returns `503`.
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
