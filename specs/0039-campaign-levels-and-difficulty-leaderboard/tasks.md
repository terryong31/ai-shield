# 0039 — Campaign levels and difficulty leaderboard: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0039`
- [x] **ENG-CAMP-001**: write failing test
- [x] **ENG-CAMP-002**: write failing test
- [x] **ENG-CAMP-003**: write failing test
- [x] **ENG-CAMP-004**: write failing test
- [x] **API-CAMP-001**: write failing test
- [x] **API-CAMP-002**: write failing test
- [x] **API-CAMP-003**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Create Supabase migration (`mise run db:migration campaign_levels_and_mastery`) and implement engine + API changes
- [ ] Regenerate OpenAPI contract & web types (`mise run contract`) + minimal web compatibility updates
- [ ] `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/engine-api.md`, `docs/reference/http-api.md`, `docs/reference/configuration.md`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
