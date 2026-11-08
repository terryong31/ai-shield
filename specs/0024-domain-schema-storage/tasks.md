# 0024 — Domain-scoped database schemas (`audit`, `game`, `players`): tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0024`
- [x] **API-SCHEMA-001**: write failing test for `audit`, `game`, `players` schemas, table definitions, RLS, and zero `public` tables in `supabase/migrations/`
- [x] **API-SCHEMA-002**: write failing test for `supabase/config.toml` exposed schemas and `supabase/seed.sql` target schema
- [x] **API-SCHEMA-003**: write failing test for `SupabaseAuditLog` querying `audit.requests` and `game.scores`
- [x] **API-SCHEMA-004**: write failing test for `SupabaseSessionStore` (`audit.clearance_sessions`) and `SupabasePlayerStore` (`players.accounts`, `players.sessions`, `players.daily_usage`)
- [x] **API-SCHEMA-005**: write failing test for `build_container` wiring all three `Supabase*` stores when configured
- [x] **API-SCHEMA-006**: write failing test for SQLite attached schemas (`audit`, `game`, `players`), empty `main` schema, and column parity with Supabase migrations
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/configuration.md`, `docs/how-to/persist-the-audit-log.md`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
