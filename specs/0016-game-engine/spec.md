# 0016: AI Defender workflow game (engine, gateway API, and web application)

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-04
- **Related:** spec 0001, spec 0006, spec 0007, spec 0011, spec 0012, spec 0015, [plan.md](plan.md), [tasks.md](tasks.md)

## Problem

1. **Fixed pipeline:** `packages/engine` runs a single hardcoded pipeline (`Classifier -> Moderation -> Debate -> ToolPolicy`). Players cannot wire their own branching boards, test custom check orders, or get scored on protection, false alarms, speed, and cost.
2. **Missing game API and scoreboard:** `apps/api` has no endpoints to list game levels, evaluate a player-built board against a level wave or custom prompt, or persist high scores in SQLite.
3. **Web layout and copy:** `apps/web` needs three clear routes (`/` landing page, `/game` interactive Vue Flow builder, and `/_console` admin-only console gated by `spec 0012` clearance sessions) styled with a high-contrast monochrome design, plain English labels, zero emojis, and zero em-dashes.

## Goals

- **Engine (`packages/engine`):**
  - Validate and execute directed acyclic defence boards (`BoardGraph`) with branching handles (`safe`, `suspicious`, `block`, `out`).
  - Add fast zero-cost checks (`WordFilterDetector`, `TextCleaner`) alongside `ClassifierDetector`, `ModerationDetector`, `DebateAdjudicator`, and `ToolPolicy`.
  - Provide three built-in levels (`easy`, `medium`, `hard`) mixing normal user messages and prompt injections.
  - Calculate a 0 to 10,000 score that rewards blocking prompt injections, fast latency, and low cost while penalising false alarms (normal messages blocked by mistake) and leaked attacks.
- **Gateway API (`apps/api`):**
  - Add `GET /api/v1/game/levels`, `POST /api/v1/game/run`, `GET /api/v1/game/scores`, `POST /api/v1/game/scores`, and admin-only `DELETE /api/v1/game/scores`.
  - Add client player authentication (`/api/v1/auth/anonymous`, `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/upgrade`, `/api/v1/auth/logout`, `/api/v1/auth/session`) supporting anonymous users and logged-in (`free` / `paid`) users, using server-side master API keys instead of client BYOK keys.
  - Regenerate the OpenAPI contract and `apps/web/app/types/api.gen.ts`.
- **Web Client (`apps/web`):**
  - `/` (`pages/index.vue`): Landing page with plain-English rules, level select cards (`Easy`, `Medium`, `Hard`), player authentication modal (`UAuthForm`), settings modal (theme selection without BYOK secrets), and top scoreboard table.
  - `/game` (`pages/game.vue`): Interactive Vue Flow defence board with check palette (locking AI agent nodes `safety_check` and `agent_review` for anonymous users), wave runner, daily quota display for logged-in free users, live counters, custom message test bar, and automatic leaderboard score recording for logged-in users.
  - `/_console` (`pages/console/index.vue`, `logs.vue`, `settings.vue`): Site-admin console gated behind `GET /api/v1/clearance` (`granted === true`), plus redirects from `/dashboard*` to `/_console*`.
  - Enforce monochrome Nuxt UI tokens, no native form/button/table tags, no emojis, and no em-dashes.

## Non-goals

- Storing user BYOK API keys on the client or server; AI model calls use server-configured master API keys.

## Behaviour

### Check types and handles

| Node kind | Plain label | Output handles | Reference time (ms) | Reference cost (USD) |
| --- | --- | --- | --- | --- |
| `incoming` | Incoming messages | `out` | `0.0` | `0.0000` |
| `word_filter` | Word filter | `safe`, `block` | `0.4` | `0.0000` |
| `text_cleanup` | Text cleanup | `out` | `1.0` | `0.0000` |
| `quick_screen` | Quick screen | `safe`, `suspicious`, `block` | `3.8` | `0.0000` |
| `safety_check` | Safety check | `safe`, `block` | `85.0` | `0.0002` |
| `agent_review` | Agent review | `safe`, `block` | `920.0` | `0.0030` |
| `tool_filter` | Tool filter | `safe`, `block` | `1.0` | `0.0000` |
| `assistant` | Assistant | terminal | `0.0` | `0.0000` |
| `blocked` | Blocked | terminal | `0.0` | `0.0000` |

### Scoring formula (0 to 10,000 points)

Given a wave with $N_{\text{attack}}$ prompt injections and $N_{\text{benign}}$ normal messages:
- `attacks_blocked` ($TP$): prompt injections ending at `blocked`.
- `attacks_leaked` ($FN$): prompt injections reaching `assistant`.
- `benign_passed` ($TN$): normal messages reaching `assistant`.
- `false_alarms` ($FP$): normal messages ending at `blocked`.

Points:
- `protection_points` = $\text{round}(5000 \times (TP / N_{\text{attack}}))$
- `accuracy_points` = $\max(0, \text{round}(2000 \times (TN / N_{\text{benign}}) - FP \times 400))$
- `speed_points` = $\text{round}(1500 \times \max(0.0, 1.0 - \text{avg\_latency\_ms} / \text{max\_latency\_ms}))$
- `cost_points` = $\text{round}(1500 \times \max(0.0, 1.0 - \text{total\_cost\_usd} / \text{max\_cost\_usd}))$
- `leak_penalty` = $FN \times 1000$
- `total_score` = $\max(0, \text{protection\_points} + \text{accuracy\_points} + \text{speed\_points} + \text{cost\_points} - \text{leak\_penalty})$

## Acceptance criteria

### Engine (`ENG`)
- **ENG-GAME-001**: `validate_board` accepts a connected acyclic board with `incoming`, `assistant`, and `blocked` nodes, and raises `BoardValidationError` when required anchor nodes are missing, edges reference unknown nodes, or a cycle exists.
- **ENG-GAME-002**: `WordFilterDetector` blocks messages matching enabled rule groups (`override`, `encoded`, `sql_tools`) and passes normal messages; `TextCleaner` decodes base64 segments, strips zero-width characters, and marks cleaned messages so downstream checks improve detection on obfuscated attacks.
- **ENG-GAME-003**: `evaluate_message` routes a message from `incoming` through connected nodes (`word_filter`, `text_cleanup`, `quick_screen`, `safety_check`, `agent_review`, `tool_filter`) to either `assistant` or `blocked`, recording every visited hop with its handle, time in milliseconds, and cost in USD.
- **ENG-GAME-004**: `get_levels` returns three built-in levels (`easy`, `medium`, `hard`), each containing a mix of normal user messages (`is_attack=False`) and prompt injections (`is_attack=True`), with latency and cost budgets.
- **ENG-GAME-005**: `score_wave` computes `total_score`, component points (`protection_points`, `accuracy_points`, `speed_points`, `cost_points`), and `medal` (`gold`, `silver`, `bronze`, `none`), reducing points whenever normal non-injection messages are blocked (`false_alarms > 0`) or injections leak (`attacks_leaked > 0`).
- **ENG-GAME-006**: On the `medium` level wave, a branching board that routes `quick_screen` (`safe -> assistant`, `block -> blocked`, `suspicious -> agent_review`) achieves a higher `total_score` (faster and cheaper with zero false alarms) than sending every message directly through `agent_review`.
- **ENG-GAME-007**: `validate_board` rejects boards that connect `incoming` directly to `assistant` or `blocked` without an intermediate tool node, and `evaluate_message` supports `ml_classifier` (trainable with allowlisted algorithms `logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest` and custom `dataset` rows), `length_limit`, and `secret_scan`, raising `BoardValidationError` for unsupported ML algorithms.

### Gateway API (`API`)
- **API-GAME-001**: `GET /api/v1/game/levels` returns `200` with the three levels (`easy`, `medium`, `hard`) and the check catalog (`word_filter`, `text_cleanup`, `quick_screen`, `safety_check`, `agent_review`, `tool_filter`).
- **API-GAME-002**: `POST /api/v1/game/run` with a valid `BoardGraph` and `level_id` returns `200` with per-message hop traces and the computed `WaveScore`; given an invalid board (cycle or missing anchor), it returns `422` with the validation message.
- **API-GAME-003**: `POST /api/v1/game/run` with a `custom_message` evaluates that single message through the submitted `BoardGraph` and returns its hop trace and outcome (`assistant` or `blocked`).
- **API-GAME-004**: `POST /api/v1/game/scores` persists a score record in SQLite, and `GET /api/v1/game/scores` returns records ordered by `total_score` descending (tie-broken by lower `avg_latency_ms` and lower `total_cost_usd`).
- **API-GAME-005**: `DELETE /api/v1/game/scores` returns `401` without a valid admin clearance session cookie, and returns `204` while clearing the scoreboard when called with a valid admin session (`Clearance.GRANTED`).
- **API-GAME-006**: `POST /api/v1/game/train` validates and trains an allowlisted `ml_classifier` algorithm (`logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`) on uploaded CSV/JSONL or row datasets and returns sample counts and training accuracy, rejecting unknown algorithms with `422`.
- **API-GAME-007**: Player auth endpoints (`/api/v1/auth/anonymous`, `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/upgrade`, `/api/v1/auth/logout`, `/api/v1/auth/session`) distinguish free anonymous users (`is_anonymous=True`, `tier="anonymous"`) from logged-in users (`is_anonymous=False`, `tier="free"` or `"paid"`): anonymous users are rejected with `403` when running boards with AI agent nodes (`safety_check`, `agent_review`) or posting scores (`POST /api/v1/game/scores`) and their wave runs are not recorded on the leaderboard; logged-in users automatically record wave scores to the leaderboard under their account name, can use AI agent nodes, and when on `tier="free"` are limited to `3` wave runs and `10` custom single-message tests per UTC day (`429` when exceeded) until upgraded to `tier="paid"`, with `GameRunRequest` accepting no client BYOK keys.

### Web Client (`WEB`)
- **WEB-GAME-001**: `/` renders the landing page with plain-English instructions, links to start `easy`, `medium`, and `hard` levels on `/game`, and the high-score table fetched from `useShieldApi().getScores()`.
- **WEB-GAME-002**: `/game` allows adding check nodes (`word_filter`, `text_cleanup`, `quick_screen`, `safety_check`, `agent_review`, `tool_filter`), connecting node handles, running a level wave or custom test message via `useShieldApi().runGame()`, and saving a completed run to the scoreboard.
- **WEB-GAME-003**: `/_console`, `/_console/logs`, and `/_console/settings` require an active admin clearance session (`granted === true`); when `granted === false`, normal users see the admin clearance login gate instead of console data, and `/dashboard*` routes redirect to `/_console*`.
- **WEB-GAME-004**: Across `apps/web/app/**/*.{vue,ts}` (excluding `types/api.gen.ts`), no Tailwind palette utilities, no native `<button>`, `<input>`, `<select>`, `<textarea>`, `<table>`, or `<dialog>` elements, no `!` important overrides, no emojis, and no em-dashes (`\u2014`) appear.
- **WEB-GAME-005**: The project is branded `ai-shield` with no client-side links to `/_console` on public pages, `/_console` is guarded by Nuxt UI `UAuthForm`, `/` serves as the game main menu with difficulty selection (showing solved status and high score) and leaderboard, and `/game` uses a two-row top nav with a quit confirmation modal (`Are you sure you want to quit? your progress will not be saved`), a `Tools` left panel, no right panel, `Safe` node label on `easy` and `Assistant` on `medium`/`hard`, live node arrival counters, and double-click node settings modals including custom ML dataset upload.
- **WEB-GAME-006**: Client pages (`/` and `/game`) provide player authentication (`usePlayerAuth()` with `UAuthForm` sign-in/sign-up and anonymous session support), remove the BYOK `Configure secrets` section from Settings on `/`, lock AI agent nodes (`safety_check`, `agent_review`) in the `/game` Tools panel for anonymous users, display remaining daily wave/test quotas for logged-in free users, and record leaderboard high scores automatically for logged-in users while hiding score saving and high score recording for anonymous users.
- **WEB-GAME-007**: Player sign-in and account creation live on a dedicated `/login` page (`pages/login.vue`) built with `UAuthForm`, with `/login?mode=register` selecting account creation. `/` contains no auth modal or `UAuthForm` and its sign-in entry points navigate to `/login`. Successful authentication returns to `/`, failed authentication stays on `/login`, and a player who is already signed in is sent to `/`. On `/`, anonymous players see no tier badge, the level selection has no `Sign in to record scores` button, and level cards show the numeric high score instead of `Not recorded (Anonymous)`.
- **WEB-GAME-008**: The `/game` `Tools` panel lays out each placeable check as a portrait `3:4` Nuxt UI `UCard` in a two-column grid showing the check name, icon, subtitle, latency and cost (`Free` when the cost is zero), with locked AI agent cards dimmed and labelled `Sign in`. Cards are operable by pointer and keyboard.
- **WEB-GAME-009**: The `/game` `Tools` panel has a fixed width with no resize handle, a hidden scrollbar (it still scrolls), and cards at least `min-w-40` wide, and its collapse control shows `i-lucide-chevron-right` when collapsed and `i-lucide-chevron-left` when expanded. Hovering or focusing a card blurs it and shows `Click or drag into canvas` (`Sign in to unlock` when locked). Unlocked cards can be dragged onto the canvas to place the node at the drop point, while locked cards cannot be dragged. Each card header has an info button that opens a modal with the tool's name, summary, latency, cost, outputs and access requirement, without placing a node.
- **WEB-GAME-010**: Settings on `/` contains only the theme selector, with no `Account tier` section. Sign-in and upgrade remain available from the main menu.
- **WEB-GAME-011**: On `/game`, the `Input` node's settings modal shows only the explanation `Connect the node with a tool and the prompt will flow into the next node.`, with no message list or connection controls. The tool info modal shows the tool name in its header, and its body shows the summary, latency and cost, with no outputs or access rows.
- **WEB-GAME-012**: Player authentication and settings live on dedicated pages: `/auth/login` (`pages/auth/login.vue`), `/auth/register` (`pages/auth/register.vue`), `/auth/recover` (`pages/auth/recover.vue`) built with `UAuthForm`, and `/settings` (`pages/settings.vue`) with a return-to-menu header alongside the `Settings` title above a `min-w-80` card containing `Theme` on the left and a `UColorModeSelect` theme selector on the right, and no modal on `/`. `POST /api/v1/auth/recover` triggers Supabase `reset_password_for_email` when configured and returns `200` with `{"status": "ok"}`.

## Security & privacy considerations

- `packages/engine` remains free of environment variables, HTTP, and storage imports.
- BYOD API keys stay in memory for the single request only and are never logged or stored in SQLite or `localStorage`.
- `/_console*` management routes and `DELETE /api/v1/game/scores` require the `HttpOnly` clearance session from spec 0012.

## Evaluation impact

Adds game level waves alongside the existing classifier benchmark without changing `ClassifierDetector` weights.

## Open questions

None.

## Verification

### 2026-11-04 · commit 489ecc5 (+ uncommitted changes)

- Criteria: ENG-GAME-001, ENG-GAME-002, ENG-GAME-003, ENG-GAME-004, ENG-GAME-005, ENG-GAME-006, API-GAME-001, API-GAME-002, API-GAME-003, API-GAME-004, API-GAME-005, WEB-GAME-001, WEB-GAME-002, WEB-GAME-003, WEB-GAME-004
- Red: 15 failing test(s) before implementation (`packages/engine/tests/test_game.py`, `packages/engine/tests/test_game.py`, `packages/engine/tests/test_game.py`)
- Green: 17 passing test(s)
- Gate: `mise run check` passed

### 2026-11-04 · commit 489ecc5 (+ uncommitted changes)

- Criteria: ENG-GAME-007, API-GAME-006, WEB-GAME-005
- Red: 3 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_direct_anchor_wire_rejected_and_trainable_ml_classifier_evaluates`, `apps/api/tests/test_game_api.py::test_train_custom_ml_classifier_endpoint_and_reject_unknown_algorithm`, `admin console access and routing [WEB-GAME-005] enforces ai-shield main menu, hidden console with UAuthForm, Safe/Assistant labels, quit modal, and double-click node settings with ML dataset upload`)
- Green: 3 passing test(s)
- Gate: `mise run check` passed

### 2026-11-04 · commit 489ecc5 (+ uncommitted changes)

- Criteria: WEB-GAME-005
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-005] enforces ai-shield main menu, hidden console with UAuthForm, Safe/Assistant labels, quit modal, and double-click node settings with ML dataset upload`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-06 · commit ce5746e (+ uncommitted changes)

- Criteria: API-GAME-007, WEB-GAME-006
- Red: 2 failing test(s) before implementation (`apps/api/tests/test_game_api.py::test_player_auth_tiers_ai_node_gate_leaderboard_recording_and_daily_quotas`, `admin console access and routing [WEB-GAME-006] enforces client player auth, removes BYOK in settings, locks AI agent nodes for anonymous users, and displays free daily quotas`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed

### 2026-11-07 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-007
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-007] moves player sign-in to a /login page with UAuthForm and removes anonymous-only UI from the main menu`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-07 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-008
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-008] renders the Tools panel as a two-column grid of portrait cards with a chevron collapse control`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-07 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-009
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-009] fixes the Tools panel width and adds a state-aware chevron, hover hint, drag to canvas, and tool info modal`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-07 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-010
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-010] removes the account tier section from Settings while keeping sign-in and upgrade on the main menu`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-011
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-011] shows only an explanation in the Input node modal and trims the tool info modal`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-012
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-012] provides dedicated /settings, /auth/login, /auth/register, and /auth/recover pages`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-012
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-012] provides dedicated /settings, /auth/login, /auth/register, and /auth/recover pages`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-GAME-012
- Red: 1 failing test(s) before implementation (`admin console access and routing [WEB-GAME-012] provides dedicated /settings, /auth/login, /auth/register, and /auth/recover pages`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
