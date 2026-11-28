# 0059 — Admin console extraction and multi-app monorepo support: tasks

- [ ] Have a human mark `spec.md` `Accepted` (and update `specs/README.md`)
- [ ] `mise run sdd:start 0059`
- [x] **DEV-SDD-001**: write failing test for multi-app `scripts/sdd.py` guards and Vitest runner
- [x] **DEV-CI-001**: write failing test for workspace, `affected.sh`, `vercel_ignore.sh`, contract, and CI wiring
- [x] **WEB-ADMIN-001**: write failing test verifying `apps/web` has no `/_console` routes
- [x] **WEB-ADMIN-002**: write failing test verifying `apps/admin` guarded routes, `noindex, nofollow`, `no-store`, and proxy
- [x] **API-ADMIN-001**: write failing test verifying production admin routes require the dedicated admin proxy secret
- [ ] `mise run sdd:red` accepted
- [ ] Implement tooling updates, `apps/admin` extraction, `apps/web` cleanup, and `apps/api` admin proxy guard; `mise run sdd:green` accepted
- [ ] Update `docs/reference/repository-layout.md`, `docs/reference/configuration.md`, `AGENTS.md`, and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
