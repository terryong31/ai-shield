# NNNN — <Feature name>: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start NNNN [IDs…]`
- [ ] **AREA-COMP-001**: write failing test
- [ ] **AREA-COMP-002**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/…`) and `CHANGELOG.md`
- [ ] Regenerate the API contract if HTTP shapes changed (`mise run contract`)
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
