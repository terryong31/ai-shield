# 0058 — Privacy policy and player data controls: tasks

Run as one SDD cycle (or split into `API-PRIV-*` and `WEB-PRIV-*` slices). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] Resolve the open question in `spec.md` (`privacyContactEmail`) and have a human mark the spec `Accepted`
- [ ] `mise run sdd:start 0058`
- [x] **API-PRIV-001**: write failing test
- [x] **API-PRIV-002**: write failing test
- [x] **API-PRIV-003**: write failing test
- [ ] **API-PRIV-004**: write failing test
- [x] **WEB-PRIV-001**: write failing test
- [x] **WEB-PRIV-002**: write failing test
- [x] **WEB-PRIV-003**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement backend export & retention pruning (`apps/api`), regenerate contract (`mise run contract`), and implement `/privacy` page, links, SEO updates, and `/settings` download (`apps/web`); `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
