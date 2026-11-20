# 0037 — LangGraph AI Agent and Tool Policy extension: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [x] `mise run sdd:start 0037 [IDs…]`
- [x] **ENG-AGENT-020**: write failing test
- [x] **ENG-TOOL-010**: write failing test
- [x] **ENG-TOOL-011**: write failing test
- [x] **ENG-TOOL-012**: write failing test
- [x] **ENG-SCORE-004**: write failing test
- [x] **API-GAME-010**: write failing test
- [x] **WEB-GAME-010**: write failing test
- [x] `mise run sdd:red` accepted
- [x] Implement; `mise run sdd:green` accepted
- [x] Update reference docs (`docs/reference/engine-api.md`, `docs/reference/http-api.md`) and `CHANGELOG.md`
- [x] Regenerate the API contract (`mise run contract`)
- [x] `mise run sdd:verify`, then `mise run sdd:done`
