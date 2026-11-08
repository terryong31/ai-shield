# 0022 — Custom sandbox: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically. Do this after 0021.

- [ ] `mise run sdd:start 0022`
- [x] **ENG-SANDBOX-001** `run_custom_wave` over a player dataset and agent
- [x] **ENG-SANDBOX-002** Dataset CSV parsing and limits
- [x] **ENG-SANDBOX-003** Custom agent profile validation
- [x] **API-SANDBOX-001** Paid players only
- [x] **API-SANDBOX-002** Per-run model client, `agent_mode: "custom"`, never recorded
- [x] **API-SANDBOX-003** The key never leaks into responses, logs or records
- [x] **API-SANDBOX-004** Provider allowlist, no base URL
- [x] **API-SANDBOX-005** Provider failure returns `502`, not counted
- [x] **WEB-SANDBOX-001** `Custom` card and route guard
- [x] **WEB-SANDBOX-002** Editable agent, model and in-memory key
- [x] **WEB-SANDBOX-003** Dataset upload, preview and errors
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update `docs/reference/http-api.md`, `engine-api.md`, `docs/explanation/threat-model.md` and `CHANGELOG.md`
- [ ] `mise run contract`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
