# 0020 — Game AI Agent: tasks

Planned as three SDD cycles; run as one cycle because the engine score change breaks the gateway and web until all three land. `mise run sdd:done` ticks the
criterion lines automatically.

## Cycle 1: engine

- [x] `mise run eval` baseline recorded
- [x] `mise run sdd:start 0020` (all criteria)
- [x] **ENG-AGENT-001** Board anchors are `incoming` and `assistant`, and a `blocked` node is rejected
- [x] **ENG-AGENT-002** An unwired output ends the trace as `blocked`
- [x] **ENG-AGENT-003** Agent prompt: objective, tools, `<player_rules>`, canary, `wrap_untrusted`, and rule limits
- [x] **ENG-AGENT-004** Attack judging: canary or forbidden tool means leaked
- [x] **ENG-AGENT-005** Benign judging: helped vs false alarm, including `expected_tool`
- [x] **ENG-AGENT-006** Non-JSON agent output fallback
- [x] **ENG-AGENT-007** Reported vs estimated tokens
- [x] **ENG-AGENT-008** New `score_wave` components
- [x] **ENG-AGENT-009** Deterministic simulated agent and `agent_mode`
- [x] **ENG-AGENT-010** Per-run canary never exposed in level data

## Cycle 2: gateway

- [x] **API-AGENT-001** Per-tier daily limits (anonymous 1, free 5, paid 300)
- [x] **API-AGENT-002** Provider failure returns `503` with no quota consumed
- [x] **API-AGENT-003** Only live runs are recorded
- [x] **API-AGENT-004** Levels expose the agent profile, and runs return agent results
- [x] **API-AGENT-005** A `blocked` node returns `422`
- [x] `mise run contract`, update `docs/reference/http-api.md`

## Cycle 3: web

- [x] **WEB-AGENT-001** Starter board with `Input` and `AI Agent` only
- [x] **WEB-AGENT-002** AI Agent modal with rules editor
- [x] **WEB-AGENT-003** Anonymous sign-in prompt before each run
- [x] **WEB-AGENT-004** New score breakdown and per-message agent results
- [x] **WEB-AGENT-005** Node redesign
- [x] **WEB-AGENT-006** Run animation and node run state
- [x] **WEB-AGENT-007** AI Agent modal redesign: tabs, read-only objective, tool rows, rules composer with suggestions
- [x] **WEB-AGENT-008** Remove the level badge and suggested rules, show plain tool names, and keep the modal scrollbar from shifting content
- [x] **WEB-AGENT-009** Apply the AI Agent modal layout to the Input and tool node modals
- [x] **WEB-AGENT-010** Latency and cost in the modal header, no Remove node or Last run, a Last wave pass/stop summary, and a star rating for the wave

## Close

- [x] `CHANGELOG.md`, `docs/reference/`, `MODEL_CARD.md` (only if eval moved)
- [x] `mise run eval` after, noted in spec
- [x] **WEB-AGENT-011** Run results confusion matrix instead of the per-node Last wave section
- [x] **ENG-AGENT-011** No block output; a block decision always stops the prompt
- [x] **WEB-AGENT-012** No Outputs form or block port, number inputs, algorithm select menu, centred larger ports
- [x] **WEB-AGENT-013** Description tooltips, centred port anchors, AI Agent modal description
- [x] **WEB-AGENT-014** Description back on board nodes; modal section help as tooltips
- [x] **WEB-AGENT-015** Attempts-left counter beside the score; no sign-in prompt before runs
- [x] **WEB-AGENT-016** Wave stats in the header beside the score; attempts counter beside Save
- [x] **WEB-AGENT-017** High Score label, plain stars, breakdown and cost/time in Run results
- [x] **WEB-AGENT-018** Run results: stars, score, New record, Show breakdown modal, clickable matrix cells
- [x] **WEB-AGENT-019** Persistent header stars to the right of High Score
- [x] **WEB-AGENT-020** Confusion matrix moves into the Score breakdown modal
- [x] **WEB-AGENT-021** Points accordion, no separator before the matrix, polished breakdown modal
