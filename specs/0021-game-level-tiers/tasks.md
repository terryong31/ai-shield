# 0021 — Game level tiers: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0021`
- [x] **ENG-LEVEL-001** Level profiles: Easy has no agent, Medium `standard`, Hard `budget`
- [x] **ENG-LEVEL-002** Easy waves never call a model
- [x] **ENG-LEVEL-003** Easy scoring weights
- [x] **ENG-LEVEL-004** Each tier calls only its own model
- [x] **ENG-LEVEL-005** Simulated agent per tier
- [x] **ENG-LEVEL-006** Lenient reply parsing for small models
- [x] **API-LEVEL-001** Catalog exposes `agent_tier` and `final_node_label`
- [x] **API-LEVEL-002** `GAME_MODEL_STANDARD` and `GAME_MODEL_BUDGET` wiring
- [x] **API-LEVEL-003** Easy runs are free of quota and recorded
- [x] **API-LEVEL-004** `score_version` on leaderboard rows
- [x] **WEB-LEVEL-001** Easy board: `Help Desk` final node
- [x] **WEB-LEVEL-002** Model section and level card labels
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update `docs/reference/engine-api.md`, `http-api.md`, `configuration.md` and `CHANGELOG.md`
- [ ] `mise run contract`
- [ ] `mise run eval` before and after, recorded in the spec
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
- [x] **WEB-LEVEL-003** Remove the model label from the level cards
- [x] **WEB-LEVEL-004** Remove the Model section from the AI Agent modal
- [x] **ENG-LEVEL-007** Final node labelled Protected Agent; validation names the final node
- [x] **WEB-LEVEL-005** Final node modal wiring hint and System Instruction heading
