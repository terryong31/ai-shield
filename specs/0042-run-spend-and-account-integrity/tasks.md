# 0042 — Run spend and account integrity: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0042 [IDs…]`
- [x] **API-SPEND-001**: write failing test
- [x] **API-SPEND-002**: write failing test
- [x] **API-SPEND-003**: write failing test
- [x] **API-SPEND-004**: write failing test
- [x] **API-SPEND-007**: write failing test
- [x] **API-SPEND-009**: write failing test
- [x] **API-SPEND-010**: write failing test
- [x] **API-SPEND-011**: write failing test
- [x] **API-SPEND-012**: write failing test
- [x] **API-SPEND-013**: write failing test
- [x] **API-SPEND-014**: write failing test
- [x] **API-SPEND-015**: write failing test
- [x] **API-SPEND-016**: write failing test
- [x] **API-SPEND-017**: write failing test
- [x] **API-SPEND-018**: write failing test
- [x] **API-SPEND-019**: write failing test
- [x] **WEB-SPEND-001**: write failing test
- [x] **WEB-SPEND-002**: write failing test
- [x] **WEB-SPEND-003**: write failing test
- [x] **API-SPEND-021**: write failing test
- [x] **API-SPEND-022**: write failing test
- [x] **WEB-SPEND-004**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/…`) and `CHANGELOG.md`
- [ ] Regenerate the API contract if HTTP shapes changed (`mise run contract`)
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
