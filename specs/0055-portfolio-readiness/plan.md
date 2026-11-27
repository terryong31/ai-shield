# 0055 — Portfolio readiness and codebase modularisation: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Deliver the work in three small, independent slices so each diff is easy to review and verify:

1. **Engine modularisation (`ENG-MOD-001`, `ENG-MOD-002`)**
   - Extract code from `packages/engine/src/shield_engine/game/__init__.py` into `types.py`, `detectors.py`, `validation.py`, `runner.py` and `scoring.py`.
   - Keep acyclic imports: `types` -> `levels`/`agent` -> `detectors`/`validation` -> `scoring` -> `runner`.
   - Re-export all public symbols in `game/__init__.py` and declare `__all__` explicitly.
   - Add a structural test in `packages/engine/tests/test_game_module_structure.py` asserting `__init__.py` line count, AST (imports/re-exports only) and public symbol completeness.

2. **Web page modularisation (`WEB-MOD-001`, `WEB-MOD-002`)**
   - Extract self-contained UI sections from `apps/web/app/pages/game.vue` into `apps/web/app/components/game/`:
     - `BoardToolbar.vue` (level header, quota/run button, save status, navigation)
     - `ToolPalette.vue` (draggable check list and level constraint badges)
     - `NodeConfigDrawer.vue` (selected node configuration, ML training upload, agent rules)
     - `WaveResultsPanel.vue` (score breakdown, stars, confusion matrix, message traces)
     - `CustomSandboxModal.vue` (custom agent, dataset CSV and BYOK form)
   - Extract stateful orchestration into `apps/web/app/composables/`:
     - `useGameBoardState.ts` (nodes, edges, save/load, dirty tracking)
     - `useGameRun.ts` (wave execution, NDJSON/result handling, anonymous retry)
   - Add a Vitest check verifying `game.vue` line count and component wiring.

3. **Onboarding and repository polish (`DEV-ONBOARD-001..003`, `DEV-POLISH-001..002`)**
   - Add a small helper script (for example `scripts/with_infisical.py`) invoked by `api:dev` and `web:dev` in `mise.toml`: when Infisical is installed and authenticated, run through `infisical run --env=<env> --path=<path> -- <cmd>`; otherwise log a short notice and run `<cmd>` directly.
   - Verify `apps/api/.env.example` and `apps/web/.env.example` match `docs/reference/configuration.md`.
   - Update `README.md` and `docs/how-to/manage-secrets.md`, record and commit `docs/assets/gameplay-demo.webp`, and delete `TODO.md`.
   - Add automated checks (pytest) for the `DEV-*` criteria.

## Interfaces

No public engine, HTTP API or database interfaces change.

```python
# packages/engine/src/shield_engine/game/__init__.py
# Re-exports only; identical public API to before this spec.
__all__: list[str]
```

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New configuration is documented in `docs/reference/configuration.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Rewrite old git commits (`asdasd`, `updates`) with `git rebase` | Rewriting `main` history breaks commit hashes referenced in specs and PRs. |
| Remove Infisical completely | Infisical is still useful for team/production secrets; automatic fallback in `dev` removes friction without losing secret management. |
| Split `levels.py` into JSON files | `levels.py` is already 672 lines after `level_waves.py` was extracted in spec 0051, and Python dataclasses keep strict typing with `mypy --strict`. |

## Risks and rollback

- **Circular imports inside `shield_engine.game`**: Mitigated by a strict acyclic dependency order (`types` at the bottom, `runner` at the top) and verified by `mypy --strict` and unit tests.
- **Vue reactivity regressions when extracting from `game.vue`**: Mitigated by keeping pure helpers in `apps/web/app/utils/` unchanged and running Vitest + Playwright E2E after each extracted component.
- **Rollback**: Every slice is a pure refactor or docs/tooling change with no schema or contract migrations; reverting the PR restores the prior layout cleanly.
