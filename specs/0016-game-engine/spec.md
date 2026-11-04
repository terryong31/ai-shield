# 0016: AI Defender workflow game (engine, gateway API, and web application)

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-04
- **Related:** spec 0001, spec 0006, spec 0007, spec 0011, spec 0012, spec 0015, [plan.md](plan.md), [tasks.md](tasks.md)

## Problem

1. **Fixed pipeline:** `packages/engine` runs a single hardcoded pipeline (`Classifier -> Moderation -> Debate -> ToolPolicy`). Players cannot wire their own branching boards, test custom check orders, or get scored on protection, false alarms, speed, and cost.
2. **Missing game API and scoreboard:** `apps/api` has no endpoints to list game levels, evaluate a player-built board against a level wave or custom prompt, or persist high scores in SQLite.
3. **Web layout and copy:** `apps/web` needs three clear routes (`/` landing page, `/game` interactive Vue Flow builder, and `/_console` admin-only console gated by `spec 0012` clearance sessions) styled with a high-contrast monochrome design, plain English labels, zero emojis, and zero em-dashes (`brainstorm/06-ui-and-copy-standard.md`).

## Goals

- **Engine (`packages/engine`):**
  - Validate and execute directed acyclic defence boards (`BoardGraph`) with branching handles (`safe`, `suspicious`, `block`, `out`).
  - Add fast zero-cost checks (`WordFilterDetector`, `TextCleaner`) alongside `ClassifierDetector`, `ModerationDetector`, `DebateAdjudicator`, and `ToolPolicy`.
  - Provide three built-in levels (`easy`, `medium`, `hard`) mixing normal user messages and prompt injections.
  - Calculate a 0 to 10,000 score that rewards blocking prompt injections, fast latency, and low cost while penalising false alarms (normal messages blocked by mistake) and leaked attacks.
- **Gateway API (`apps/api`):**
  - Add `GET /api/v1/game/levels`, `POST /api/v1/game/run`, `GET /api/v1/game/scores`, `POST /api/v1/game/scores`, and admin-only `DELETE /api/v1/game/scores`.
  - Support optional in-memory BYOD model settings per run without storing user API keys.
  - Regenerate the OpenAPI contract and `apps/web/app/types/api.gen.ts`.
- **Web Client (`apps/web`):**
  - `/` (`pages/index.vue`): Landing page with plain-English rules, level select cards (`Easy`, `Medium`, `Hard`), and top scoreboard table.
  - `/game` (`pages/game.vue`): Interactive Vue Flow defence board with check palette, wave runner, live counters, custom message test bar, BYOD model settings drawer, and score submission dialog.
  - `/_console` (`pages/console/index.vue`, `logs.vue`, `settings.vue`): Site-admin console gated behind `GET /api/v1/clearance` (`granted === true`), plus redirects from `/dashboard*` to `/_console*`.
  - Enforce monochrome Nuxt UI tokens, no native form/button/table tags, no emojis, and no em-dashes.

## Non-goals

- Multi-user accounts or storing user BYOD API keys on disk.

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

### Web Client (`WEB`)
- **WEB-GAME-001**: `/` renders the landing page with plain-English instructions, links to start `easy`, `medium`, and `hard` levels on `/game`, and the high-score table fetched from `useShieldApi().getScores()`.
- **WEB-GAME-002**: `/game` allows adding check nodes (`word_filter`, `text_cleanup`, `quick_screen`, `safety_check`, `agent_review`, `tool_filter`), connecting node handles, running a level wave or custom test message via `useShieldApi().runGame()`, and saving a completed run to the scoreboard.
- **WEB-GAME-003**: `/_console`, `/_console/logs`, and `/_console/settings` require an active admin clearance session (`granted === true`); when `granted === false`, normal users see the admin clearance login gate instead of console data, and `/dashboard*` routes redirect to `/_console*`.
- **WEB-GAME-004**: Across `apps/web/app/**/*.{vue,ts}` (excluding `types/api.gen.ts`), no Tailwind palette utilities, no native `<button>`, `<input>`, `<select>`, `<textarea>`, `<table>`, or `<dialog>` elements, no `!` important overrides, no emojis, and no em-dashes (`\u2014`) appear.
- **WEB-GAME-005**: The project is branded `ai-shield` with no client-side links to `/_console` on public pages, `/_console` is guarded by Nuxt UI `UAuthForm`, `/` serves as the game main menu with difficulty selection (showing solved status and high score) and leaderboard, and `/game` uses a two-row top nav with a quit confirmation modal (`Are you sure you want to quit? your progress will not be saved`), a `Tools` left panel, no right panel, `Safe` node label on `easy` and `Assistant` on `medium`/`hard`, live node arrival counters, and double-click node settings modals including custom ML dataset upload.

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
