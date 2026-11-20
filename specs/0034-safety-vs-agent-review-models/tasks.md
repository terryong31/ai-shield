# Tasks — 0034 Distinct Safety check vs Agent review

- [ ] Human review & mark `specs/0034-safety-vs-agent-review-models/spec.md` as `Accepted`
- [ ] `mise run sdd:start 0034`
- [x] **ENG-CHECK-001** `safety_check` supports guardrail verdicts (`safe`/`unsafe`/`Yes`/`No`/JSON) and per-model routing
- [x] **ENG-CHECK-002** `agent_review` passes player-written `config.prompt` instructions in system prompt and validates length
- [x] **WEB-CHECK-001** Both `safety_check` and `agent_review` use `USelectMenu` with distinct model lists and `agent_review` includes a prompt/instruction textarea
