# 0055 — Portfolio readiness and codebase modularisation

- **Status:** Implemented
- **Area:** ENG | WEB | DEV
- **Owner:** Terry Ong
- **Created:** 2026-11-27
- **Related:** [ADR 0002](../../docs/explanation/decisions/0002-engine-gateway-split.md), [ADR 0008](../../docs/explanation/decisions/0008-infisical-for-secrets.md), [0051](../0051-campaign-levels-v2/spec.md)

## Problem

A code review of the repository for portfolio presentation found four gaps that hurt first impressions and maintainability:

1. `packages/engine/src/shield_engine/game/__init__.py` holds 2,210 lines of implementation across types, detectors, validation, wave execution and scoring. Putting core logic in `__init__.py` makes the package hard to navigate.
2. `apps/web/app/pages/game.vue` holds 2,822 lines in one Vue page component. This mixes board state, run orchestration, node configuration, custom sandbox forms and results rendering in one file.
3. `README.md` lists `infisical login` (private project access) as a required installation step. External reviewers who clone the repository cannot run `mise run dev` without Infisical access, even though the game works without provider keys.
4. The repository root still contains a casual `TODO.md`, and `README.md` shows only a static screenshot instead of a short gameplay recording that demonstrates drag, wire and run flow.

## Goals

- Keep `packages/engine/src/shield_engine/game/__init__.py` as a thin public re-export module and move implementation into focused submodules, with no public API breakage.
- Split `apps/web/app/pages/game.vue` into focused Nuxt UI components and composables, with no behaviour change.
- Give external contributors and reviewers a one-command local startup path that works without an Infisical account or external API keys, documented in `README.md`.
- Remove root `TODO.md`, add a short gameplay recording to `README.md`, and link key engineering artifacts (ADRs, OpenAPI contract, model card) from `README.md`.

## Non-goals

- Rewriting git commit history on `main`.
- Changing game rules, scoring formulas, HTTP API contracts or database schemas.
- Splitting `packages/engine/src/shield_engine/game/levels.py` further (wave data was already extracted to `level_waves.py` in spec 0051).
- Redesigning the defence board for mobile screens (track as a separate spec or issue).

## Behaviour

### Engine modularisation (`ENG`)

`packages/engine/src/shield_engine/game/__init__.py` contains only module docstring, re-exports and `__all__`. All implementation moves to dedicated submodules under `packages/engine/src/shield_engine/game/`:

| Module | Responsibility |
| --- | --- |
| `types.py` | Frozen dataclasses (`BoardNode`, `BoardEdge`, `BoardGraph`, `HopTrace`, `MessageTrace`, `WaveScore`, `FairScore`, `PathStep`, `RunStop`, `WaveResult`, `CheckDefinition`, `FittedClassifier`, `TrainingSummary`), `BoardValidationError`, check catalogue |
| `detectors.py` | `WordFilterDetector`, `TextCleaner`, training-row validation, CSV parsing and scikit-learn classifier fitting |
| `validation.py` | `validate_board`, `validate_board_for_level`, tool policy config checks |
| `runner.py` | `evaluate_message`, `run_wave`, `run_single_message`, routing and response-parsing helpers |
| `scoring.py` | `score_wave`, `score_traces`, `fair_score`, `score_campaign`, list-price and follow-up helpers |

Every existing public symbol imported from `shield_engine.game` stays available at the same import path and keeps the same signature and runtime behaviour.

### Web page modularisation (`WEB`)

`apps/web/app/pages/game.vue` acts as a thin page coordinator that composes focused subcomponents under `apps/web/app/components/game/` and composables under `apps/web/app/composables/`. All UI continues to use Nuxt UI and Vue Flow components only.

### Local onboarding without Infisical (`DEV`)

`mise run dev` (`api:dev` and `web:dev`) checks whether an authenticated Infisical session is available. When Infisical is authenticated, it runs with `infisical run` as before. When Infisical is not installed or not authenticated, it prints a short notice and falls back automatically to local mode without `infisical run`: it reads optional local overrides from `apps/api/.env` and `apps/web/.env` (documented by the existing `.env.example` files) and starts the game in offline/default mode when provider keys are unset.

`README.md` **Getting started** documents `mise run dev` as working out of the box without Infisical access, and lists `infisical login` as optional for team members with project access.

### Repository polish (`DEV`)

- Delete `TODO.md` at the repository root after moving open items to GitHub Issues.
- Add a lightweight animated WebP gameplay recording (`docs/assets/gameplay-demo.webp`, 20 to 30 seconds, under 5 MB) in `README.md` under **About the project**, showing a player dragging a check, wiring it and running a wave.
- Add an **Engineering highlights** subsection in `README.md` linking to [Architecture](../../docs/explanation/architecture.md), [ADRs](../../docs/explanation/decisions/README.md), [OpenAPI contract](../../contracts/shield-api.openapi.json) and [Model card](../../packages/engine/MODEL_CARD.md).

## Acceptance criteria

- **ENG-MOD-001**: Given `packages/engine/src/shield_engine/game/__init__.py`, then it has 150 lines or fewer, defines no classes or functions of its own, and exports the complete `__all__` public surface from the submodules (`types`, `detectors`, `validation`, `runner`, `scoring`, `levels`, `agent`, `custom`, `model_signing`).
- **ENG-MOD-002**: Given all existing imports from `shield_engine.game` across `packages/engine`, `apps/api` and tests, when the full Python test suite and `mypy --strict` run, then every import resolves and every test passes with no public API change.
- **WEB-MOD-001**: Given `apps/web/app/pages/game.vue`, then it has 600 lines or fewer, and its extracted panels and composables live under `apps/web/app/components/game/` and `apps/web/app/composables/`.
- **WEB-MOD-002**: Given the refactored game page, when all Vitest unit tests, `vue-tsc` and Playwright E2E tests run, then all tests pass with no behaviour regression.
- **DEV-ONBOARD-001**: Given the local dev runner wrapper used by `api:dev` and `web:dev` in `mise.toml`, when Infisical is not configured or not authenticated, then it falls back to running the command directly without `infisical run` and logs a short notice.
- **DEV-ONBOARD-002**: Given a clean environment with no Infisical session and no provider API keys, when `apps/api` starts via the local dev configuration, then `/api/v1/health` returns `200` and the game serves campaign levels without crashing.
- **DEV-ONBOARD-003**: Given `README.md`, then **Getting started** documents `mise run dev` without requiring private Infisical access and references `.env.example` for optional local overrides.
- **DEV-POLISH-001**: Given the repository root, then `TODO.md` does not exist.
- **DEV-POLISH-002**: Given `README.md`, then it embeds `docs/assets/gameplay-demo.webp` (committed, size 5 MB or less) and links to the ADRs, OpenAPI contract and model card.

## Security & privacy considerations

- Local fallback applies only to `api:dev` and `web:dev` (`APP_ENV=development`) and must never be used in production. Production startup guards (`TRUSTED_PROXY_SECRET`, `MODEL_SIGNING_KEY`) stay unchanged and fail closed.
- `.env.example` files contain placeholder values only. `.env` files remain git-ignored and scanned by `gitleaks`.
- The gameplay recording must not show real emails, API keys or production secrets.

## Evaluation impact

No change to detection logic, classifiers or scoring. `mise run check` (including all engine, API, web tests and calibration report checks) must stay green with identical scores.

## Open questions

None.

- Decided on 2026-11-27: `mise run dev` (`api:dev` and `web:dev`) falls back automatically to local mode when Infisical is not configured or authenticated.
- Decided on 2026-11-27: gameplay recording uses animated WebP (`docs/assets/gameplay-demo.webp`).

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: ENG-MOD-001, ENG-MOD-002, WEB-MOD-001, WEB-MOD-002, DEV-ONBOARD-001, DEV-ONBOARD-002, DEV-ONBOARD-003, DEV-POLISH-001, DEV-POLISH-002
- Red: 10 failing test(s) before implementation (`packages/engine/tests/test_game_modules.py::test_package_init_only_re_exports`, `packages/engine/tests/test_game_modules.py::test_every_import_from_the_package_resolves`, `Game page modules (spec 0055) [WEB-MOD-001] keeps game.vue at 600 lines or fewer, with its panels and state split out`)
- Green: 10 passing test(s)
- Gate: `mise run check` passed

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: WEB-MOD-002
- Red: 1 failing test(s) before implementation (`Game page modules (spec 0055) [WEB-MOD-002] shares one page state with every panel through provide and inject`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
