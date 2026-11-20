# 0025 — Account settings: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0025 [IDs…]`
- [x] **API-ACCOUNT-001** New password works, old one fails
- [x] **API-ACCOUNT-002** Password change revokes other sessions
- [x] **API-ACCOUNT-003** Email change moves login and data
- [x] **API-ACCOUNT-004** Email taken `409`, same email `422`
- [x] **API-ACCOUNT-005** Usage merge keeps the larger count
- [x] **API-ACCOUNT-006** Reset deletes own scores and boards, keeps usage
- [x] **API-ACCOUNT-007** Same-name accounts keep their own scores
- [x] **API-ACCOUNT-008** Delete account removes data and clears the cookie
- [x] **API-ACCOUNT-009** Re-register the same day keeps usage
- [x] **API-ACCOUNT-010** Wrong `confirm` returns `422`
- [x] **API-ACCOUNT-011** No or anonymous session returns `403`
- [x] **API-ACCOUNT-012** Wrong password `401`, 5 failures `429`
- [x] **API-ACCOUNT-013** Invalid bodies `422`
- [x] **API-ACCOUNT-014** No passwords or hashes in responses or logs
- [x] **API-ACCOUNT-015** Mid-way store failure returns `503`, old login still works
- [x] **API-ACCOUNT-016** Store parity (in-memory, SQLite, Supabase fake)
- [x] **API-ACCOUNT-017** `game.scores.email` migration, SQLite mirror, email-keyed upsert
- [x] **API-ACCOUNT-018** Leaderboard never returns the email
- [x] **WEB-ACCOUNT-001** `Account` card on `/settings`
- [x] **WEB-ACCOUNT-002** Email and password modals
- [x] **WEB-ACCOUNT-003** Reset and delete confirmation modals
- [x] **WEB-ACCOUNT-004** Post-success flows
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Migration via `mise run db:migration account_score_email`
- [ ] Regenerate the API contract (`mise run contract`)
- [ ] Update `docs/reference/http-api.md`, `docs/reference/configuration.md` (`local:db:reset`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
