# 0055 — Portfolio readiness and codebase modularisation: tasks

Run as one SDD cycle (or three slices: `ENG`, `WEB`, `DEV`). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0055`
- [x] **ENG-MOD-001**: write failing test for `shield_engine/game/__init__.py` structure and line limit
- [x] **ENG-MOD-002**: write failing test asserting complete public exports from `shield_engine.game` submodules
- [x] **WEB-MOD-001**: write failing test for `apps/web/app/pages/game.vue` line limit and extracted components
- [x] **WEB-MOD-002**: verify existing Vitest and E2E suites cover refactored game page flows
- [x] **DEV-ONBOARD-001**: write failing test checking `api:dev` / `web:dev` Infisical wrapper falls back cleanly to local mode
- [x] **DEV-ONBOARD-002**: write failing test verifying API health and levels boot without Infisical or provider keys
- [x] **DEV-ONBOARD-003**: write failing test checking `README.md` documents `mise run dev` without private Infisical access
- [x] **DEV-POLISH-001**: write failing test asserting root `TODO.md` does not exist
- [x] **DEV-POLISH-002**: write failing test checking `README.md` embeds `docs/assets/gameplay-demo.webp` (<= 5 MB) and engineering links
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/repository-layout.md`, `docs/reference/cli-and-tasks.md`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
