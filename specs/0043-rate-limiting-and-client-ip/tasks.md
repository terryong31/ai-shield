# 0043 — Rate limiting, trusted client IP, bot protection and production configuration: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0043 [IDs…]`
- [x] **API-RATE-001**: write failing test
- [x] **API-RATE-002**: write failing test
- [x] **API-RATE-003**: write failing test
- [x] **API-RATE-004**: write failing test
- [x] **API-RATE-005**: write failing test
- [x] **API-RATE-006**: write failing test
- [x] **API-RATE-007**: write failing test
- [x] **API-RATE-008**: write failing test
- [x] **API-RATE-009**: write failing test
- [x] **API-RATE-010**: write failing test
- [x] **API-RATE-011**: write failing test
- [x] **API-RATE-012**: write failing test
- [x] **API-RATE-013**: write failing test
- [x] **API-RATE-014**: write failing test
- [x] **API-IP-001**: write failing test
- [x] **API-IP-002**: write failing test
- [x] **API-IP-003**: write failing test
- [x] **API-IP-004**: write failing test
- [x] **API-IP-005**: write failing test
- [x] **WEB-RATE-001**: write failing test
- [x] **WEB-RATE-002**: write failing test
- [x] **WEB-RATE-003**: write failing test
- [x] **WEB-RATE-004**: write failing test
- [x] **WEB-BOTID-001**: write failing test
- [x] **WEB-BOTID-002**: write failing test
- [x] **WEB-BOTID-003**: write failing test
- [x] **WEB-BOTID-004**: write failing test
- [x] **WEB-BOTID-005**: write failing test
- [x] **WEB-BOTID-006**: write failing test
- [x] **API-BOTID-001**: write failing test
- [x] **API-BOTID-002**: write failing test
- [x] **API-BOTID-003**: write failing test
- [x] **API-BOTID-004**: write failing test
- [x] **API-BOTID-005**: write failing test
- [x] **API-BOTID-006**: write failing test
- [x] **API-PROD-002**: write failing test
- [x] **API-PROD-006**: write failing test
- [x] **API-PROD-007**: write failing test
- [x] **API-PROD-005**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/…`) and `CHANGELOG.md`
- [ ] Regenerate the API contract if HTTP shapes changed (`mise run contract`)
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
