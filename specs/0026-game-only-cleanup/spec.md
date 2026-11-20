# 0026 — Game-only cleanup: remove the legacy chatbot stack

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-09
- **Related:** supersedes 0001, 0003–0006, 0008, 0009, 0011, 0013, 0014; narrows 0002, 0007, 0012, 0016, 0024; keeps 0010, 0015, 0020–0023, 0025

## Problem

The repository still carries the original product, a protected chatbot. It
includes the screening pipeline, moderation, LLM debate, tool policy, the
`/chat` NDJSON stream, the demo assistant and its tools, screen and predict
endpoints, the feedback CSV, the request audit log with its stats and the eval
harness. None of the game uses it. No web page renders the chat UI. Yet the
endpoints remain public, keep LLM calls reachable and take up most of the
code, tests, docs and specs. The owner wants only what the game needs, plus an
admin console that monitors the game.

## Goals

- Every remaining public route, page, module and setting serves the game or its
  admin console.
- The engine becomes the game's check library and keeps only what the game
  calls.
- The admin console (`/_console`, passphrase clearance) stays and shows only
  game data.
- Docs, specs, `AGENTS.md`, the contract and `mise` tasks describe the game-only
  repository, and the full gate passes.

## Non-goals

- New game features or new admin metrics beyond what the console can show
  from existing game endpoints. Richer monitoring gets its own spec.
- Changing game behaviour, scoring, quotas or the saved-board format.
- Rewriting player accounts or moving to Supabase Auth (see 0025 and any
  follow-up spec).

## Behaviour

### Kept

| Area | Kept |
| --- | --- |
| HTTP | `GET /health`; `/auth/*` (player auth, upgrade, recover); `/game/*` (levels, run, train, saves, scores including the admin-only `DELETE /game/scores`); `POST/GET/DELETE /clearance` (admin console sign-in) |
| Engine | `shield_engine.game` (levels, scoring, agent, custom sandbox), the ML classifier detector and baseline model loading, the custom classifier training the game's ML filter uses, the dataset loader that training needs, `ports` (`Classifier`, `ChatModel`, `UsageChatModel`, messages), the Groq adapter, `wrap_untrusted`, and the `testing` fakes the remaining tests use |
| Gateway | the container wiring for the classifier, game agents (Gemini standard, Groq budget), BYOK adapter, player store, score store, clearance sessions and attempt limiter |
| Web | `/`, `/game`, `/plans`, `/settings`, `/auth/*`, and `/_console` (Overview and Settings) |
| Storage | `audit.clearance_sessions`, `game.scores`, `game.saved_boards`, `players.*` |

### Removed

| Area | Removed |
| --- | --- |
| HTTP | `POST /chat`, `POST /screen`, `POST /predict`, `GET /requests`, `GET /stats`, `POST /feedback`, and their request/response/event schemas (the `ChatEvent` union, `Mode`, screening and stats models) |
| Engine | `Shield` pipeline and `ShieldConfig`, moderation detector, debate and fallback adjudication (except `wrap_untrusted`, which moves to its own module), tool policy (`ToolPolicy`, `ToolSpec`, `RiskLevel`, `allowed_tools`), pipeline events, feedback store, the CLI, the evaluation runner and metrics, and their exports and tests. `Clearance` moves to the gateway, the only place that uses it |
| Gateway | `services/chat.py`, `services/access.py`, the demo assistant and demo tools, the feedback CSV, the request audit log (`audit.requests` in SQLite and Supabase) and settings only they used (for example `GROQ_GUARD_MODEL`, `GROQ_DEBATE_MODEL`, `FEEDBACK_PATH`) |
| Web | `ChatInterface`, dashboard stats and pipeline components, the legacy workflow nodes (`AgentNode`, `DualAgentNode`, `MLNode`, `NodeContainer`, `OblivionNode`, `SwitchNode`, `ToolboxNode`, `UserNode`, `WorkflowVisualizer`), `useByodSecrets`, `useSecurityMode`, `useShieldWorkflow`, `utils/chatStream.ts`, `utils/audit.ts`, `utils/pipelineGraph.ts`, `types/workflow.ts`, the `/dashboard/*` redirect pages, `/_console/logs`, and `streamChat` / audit / stats methods in `useShieldApi()` |
| Tooling | `mise run eval` and the eval baseline, and the research tasks that only fed the chatbot |
| Database | a new migration drops `audit.requests`; `supabase/seed.sql` stops seeding it |

### Admin console after cleanup

| Page | Shows |
| --- | --- |
| `/_console` Overview | stat tiles computed from the latest scores: scores recorded, players on the board, scores per level and medals; the recent scores table; `Clear scoreboard` (calls `DELETE /game/scores`) |
| `/_console/settings` | appearance, plus the admin session with `Sign out` |
| Sidebar | Overview, Settings, Main menu |

Without admin clearance, every console page shows the existing `Admin access
required` empty state.

### Specs and docs

- Specs whose behaviour is entirely removed (0001, 0003–0006, 0008, 0009, 0011,
  0013, 0014) get the status `Superseded by 0026`.
- Specs that are partly removed (0002, 0007, 0012, 0016, 0024) keep their status. Their
  removed criteria move to a `Retired by 0026` list without the bold criterion
  form, so `spec:check` no longer expects tests for them.
- Implementation note: the first draft listed 0002 as superseded and 0009 as
  narrowed. Applying the rule above, 0002 (the classifier, still used by the
  game's ML filter) is narrowed and 0009 (the request audit log) is
  superseded; 0012 and 0024 are narrowed because some of their criteria named
  `/chat` or `audit.requests`.
- `AGENTS.md`, `README.md`, `docs/` (tutorials, how-tos, reference,
  explanation, ADRs and the threat model), `packages/engine/MODEL_CARD.md` and
  `CHANGELOG.md` describe the game-only repository. ADRs for removed designs
  are marked superseded rather than deleted.

## Acceptance criteria

- **API-CLEAN-001**: Given the gateway, when the removed routes are requested (`POST /api/v1/chat`, `POST /api/v1/screen`, `POST /api/v1/predict`, `GET /api/v1/requests`, `GET /api/v1/stats`, `POST /api/v1/feedback`), then each returns `404`, and the exported contract lists only `/health`, `/auth/*`, `/game/*` and `/clearance` paths.
- **API-CLEAN-002**: Given the regenerated contract, when its component schemas are listed, then no chat event, screening, prediction, stats, feedback or mode schema remains.
- **API-CLEAN-003**: Given the kept routes, when the existing game, auth, saves, custom sandbox, clearance and health tests run, then they pass unchanged (the cleanup changes no game behaviour).
- **API-CLEAN-004**: Given SQLite and Supabase (fake client) storage, when the gateway starts and records a score, then no `audit.requests` table is created or used, and a migration drops `audit.requests` from Postgres.
- **ENG-CLEAN-001**: Given the engine package, when its public API (`shield_engine.__all__`) is listed, then it contains no pipeline, moderation, debate, tool-policy, event, feedback, evaluation-runner or clearance names, and `wrap_untrusted` is still importable and still wraps untrusted text.
- **ENG-CLEAN-002**: Given the engine source and the gateway, when scanned, then no module imports a removed engine module, and the engine still never imports `fastapi`, `supabase` or `shield_api`.
- **WEB-CLEAN-001**: Given the web app, when its files are listed, then none of the removed components, composables, utils, types or pages exist, and `useShieldApi()` exposes no chat, screen, audit, stats or feedback method.
- **WEB-CLEAN-002**: Given an admin on `/_console`, when it renders, then the sidebar shows only Overview, Settings and Main menu, and the Overview shows score-based stat tiles, the recent scores table and `Clear scoreboard`, with no request stats, pipeline view or audit log link.
- **REPO-CLEAN-001**: Given the repository, when `mise tasks` is listed, then there is no `eval` task; the specs listed above carry `Superseded by 0026` or a `Retired by 0026` list; and `mise run check` passes.

## Security & privacy considerations

- The attack surface shrinks: the public `/chat`, `/screen` and `/predict`
  routes, which let anyone trigger server-side LLM calls with the server's
  keys, are gone.
- The request audit log, which stored user prompts, is removed and its table
  dropped. Existing rows are deleted by the migration, so back them up first
  if you need them.
- Admin clearance, session hashing and the failed-attempt limiter stay as they
  are, guarding the console and `DELETE /game/scores`.
- `wrap_untrusted` stays, so the game agent still treats prompts as data.

## Evaluation impact

The eval harness and its recorded baseline are removed, so no `mise run eval`
numbers are produced any more. The game's own scoring (spec 0020/0021) is
unchanged. `MODEL_CARD.md` keeps the baseline classifier's documented
performance as historical data.

## Open questions

None. Decisions the owner may overturn before accepting: the eval harness is
removed rather than kept as a standalone benchmark; `audit.requests` data is
dropped, not archived; ADRs are marked superseded, not deleted.

## Verification

### 2026-11-09 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-CLEAN-001, API-CLEAN-002, API-CLEAN-003, API-CLEAN-004, ENG-CLEAN-001, ENG-CLEAN-002, WEB-CLEAN-001, WEB-CLEAN-002, REPO-CLEAN-001
- Red: 23 failing test(s) before implementation (`apps/api/tests/test_game_only_api.py::test_removed_routes_return_404[post-/api/v1/chat]`, `apps/api/tests/test_game_only_api.py::test_removed_routes_return_404[post-/api/v1/screen]`, `apps/api/tests/test_game_only_api.py::test_removed_routes_return_404[post-/api/v1/predict]`)
- Green: 35 passing test(s)
- Gate: `mise run check` passed
