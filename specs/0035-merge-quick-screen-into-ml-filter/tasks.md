# 0035 — Merge Quick screen into ML filter: tasks

Run as one SDD cycle. `mise run sdd:done` ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0035 ENG-ML-001 ENG-ML-002 API-ML-001 WEB-ML-001`
- [x] **ENG-ML-001**: write failing test
- [x] **ENG-ML-002**: write failing test
- [x] **API-ML-001**: write failing test
- [x] **WEB-ML-001**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement; update contract (`mise run contract`); `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/`, `packages/engine/MODEL_CARD.md`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
