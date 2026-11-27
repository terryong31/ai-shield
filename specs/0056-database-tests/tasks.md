# 0056 — Database tests: tasks

Run as one SDD cycle (or separate slices for pgTAP vs Python integration). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0056`
- [ ] Confirm adding `psycopg[binary]` to `apps/api/pyproject.toml` dev dependencies and updating `.github/workflows/ci.yml`
- [ ] **API-DB-001**: write failing test
- [ ] **API-DB-002**: write failing test
- [ ] **API-DB-003**: write failing test
- [ ] **API-DB-004**: write failing test
- [ ] **API-DB-005**: write failing test
- [ ] **API-DB-006**: write failing test
- [ ] **API-DB-007**: write failing test
- [x] **DEV-DB-001**: write failing test
- [x] **DEV-DB-002**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement pgTAP suite (`supabase/tests/`), Python DB tests (`apps/api/tests/db/`), `mise.toml` `test:db`, and CI `migrations` step; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
