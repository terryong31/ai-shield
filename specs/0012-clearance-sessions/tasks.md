# 0012 — Clearance sessions: tasks

One SDD cycle. `mise run sdd:done` ticks the criterion lines automatically.
Must land **before** spec 0011 slice 1 (WEB-CLEAR-001 depends on it).

- [ ] `mise run sdd:start 0012`
- [x] **API-CLEAR-001**: write failing test
- [x] **API-CLEAR-002**: write failing test
- [x] **API-CLEAR-003**: write failing test
- [x] **API-CLEAR-004**: write failing test (with 011, replaces the API-CHAT-003 test in `test_chat.py`)
- [x] **API-CLEAR-005**: write failing test
- [x] **API-CLEAR-006**: write failing test
- [x] **API-CLEAR-007**: write failing test
- [x] **API-CLEAR-008**: write failing test
- [x] **API-CLEAR-009**: write failing test
- [x] **API-CLEAR-010**: write failing test
- [x] **API-CLEAR-011**: write failing test
- [x] **API-CLEAR-012**: write failing test
- [x] **API-CLEAR-013**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement `services/sessions.py`, `routers/clearance.py`, `access.clearance_for`, settings, container wiring, CORS
- [ ] `mise run contract`; commit `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`
- [ ] Rewrite the API-CHAT-003 line in spec 0007 exactly as given in spec 0012's Security section
- [ ] Update `docs/reference/http-api.md`, `docs/reference/configuration.md`, `apps/api/AGENTS.md`, `CHANGELOG.md` (*Changed*: breaking)
- [ ] `mise run sdd:green`, `mise run sdd:verify`, `mise run sdd:done`
