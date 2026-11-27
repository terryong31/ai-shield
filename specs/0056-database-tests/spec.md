# 0056 — Database tests

- **Status:** Implemented
- **Area:** API | DEV
- **Owner:** Terry Ong
- **Created:** 2026-11-27
- **Related:** [ADR 0004](../../docs/explanation/decisions/0004-frontend-talks-only-to-gateway.md), [0024-domain-schema-storage](../0024-domain-schema-storage/spec.md), [0042-run-spend-and-account-integrity](../0042-run-spend-and-account-integrity/spec.md), [0046-remove-sqlite-supabase-only](../0046-remove-sqlite-supabase-only/spec.md), [0049-stripe-pass-checkout](../0049-stripe-pass-checkout/spec.md)

## Problem

Database checks in `apps/api/tests/test_domain_schemas.py` currently rely on regex scans of `.sql` migration files and an in-memory `FakeClient`. As a result, real PostgreSQL behaviour is untested before deployment:

1. **RLS and privilege boundaries are inferred, not executed.** Regex checks cannot catch a missing `REVOKE`, an accidental default privilege grant, or a PostgREST role (`anon`, `authenticated`) reading `audit`, `game`, or `players` tables or invoking RPCs.
2. **PL/pgSQL RPCs have zero live execution tests.** Five concurrency-critical functions (`players.reserve_daily_usage`, `players.release_daily_usage`, `players.fulfil_purchase`, `players.revoke_purchase`, and `players.restore_purchase`) use `FOR UPDATE` row locks, `ON CONFLICT ... DO UPDATE`, interval arithmetic, and `set search_path = ''`. `FakeClient` cannot validate SQL syntax, type casts, lock behaviour, or edge cases.
3. **Partial unique indexes and `CHECK` constraints are unverified.** `purchases_one_pending_idx`, `purchases_payment_intent_idx`, and table `CHECK` constraints are never exercised against PostgreSQL error code `23505` or constraint violations.
4. **Concurrency races are not tested against real transactions.** Simultaneous `reserve_daily_usage` or `fulfil_purchase` calls must be proven serializable under real parallel PostgreSQL connections.
5. **PostgREST adapter parity is untested.** `SupabaseScoreStore`, `SupabasePlayerStore`, and `SupabaseSessionStore` have never been exercised end-to-end against live PostgREST (`supabase start`) to verify schema headers, `.rpc(...)` return shapes, `on_conflict` upserts, and `delete_account` / `move_email` behaviour.

## Goals

- Establish a two-layer database test pyramid against local Supabase (`supabase start`):
  1. **pgTAP SQL unit tests (`supabase/tests/*.sql`)** run via `supabase test db` for schema lock-down, RLS enforcement across roles, `CHECK` constraints, indexes, and PL/pgSQL RPC state transitions.
  2. **Python PostgreSQL + PostgREST integration and concurrency tests (`apps/api/tests/db/`)** marked `@pytest.mark.db` for multi-connection race conditions and full `SupabaseScoreStore` / `SupabasePlayerStore` / `SupabaseSessionStore` contract parity.
- Keep default unit tests (`mise run test:api`) fast, deterministic, and Docker-free by excluding `@pytest.mark.db` unless `mise run test:db` runs.
- Run both pgTAP and Python DB integration tests in CI (`migrations` job) so broken migrations, leaky RLS, or RPC regressions cannot merge.

## Non-goals

- Running database tests against a hosted or production Supabase project (all DB tests target ephemeral local Supabase only).
- Replacing existing fast unit tests that use `InMemory*Store` and `FakeClient`.
- Benchmarking database throughput under high request volume (covered by spec 0057).

## Behaviour

### 1. Layer 1 — pgTAP SQL test suite (`supabase/tests/`)

| Test file | Scope |
| --- | --- |
| `01_rls_and_privileges.sql` | Dynamic introspection over `audit`, `game`, and `players`: verifies every table has RLS enabled, zero `public` application tables exist, `anon` and `authenticated` have zero table/schema/function privileges, and `service_role` can read/write and execute RPCs. |
| `02_constraints_and_indexes.sql` | Verifies `CHECK` constraints (`game.scores.medal`, `players.accounts.tier`, `players.purchases.status`), `purchases_one_pending_idx` (one pending per `(email, livemode)`, multiple non-pending allowed), `purchases_payment_intent_idx` (multiple `NULL` allowed, duplicate non-null rejected), and `scores_rank_idx` / `scores_owner_idx` existence. |
| `03_daily_usage_rpcs.sql` | Exercises `players.reserve_daily_usage` and `players.release_daily_usage`: first insert, increment up to `p_limit`, denial at `p_limit`, `p_limit <= 0`, invalid `p_kind` exception, and floor at `0` on release. |
| `04_purchase_rpcs.sql` | Exercises `players.fulfil_purchase`, `players.revoke_purchase`, and `players.restore_purchase`: `pending`/`expired` -> `paid`, `duplicate`, `mismatch`, `orphaned`, `no_account`, `unknown`, unused-interval calculation, stacked future pass shifting (`starts_at >= ends_at`), and restore after failed refund / won dispute. |

Every pgTAP file runs inside `BEGIN; ... SELECT * FROM finish(); ROLLBACK;` so tests leave zero persistent rows.

### 2. Layer 2 — Python concurrency and PostgREST integration tests (`apps/api/tests/db/`)

- **True concurrency tests (direct Postgres connections via `psycopg`):**
  - Launch `N` parallel connections (e.g., 16 threads/tasks with barrier synchronization) calling `players.reserve_daily_usage` with `p_limit = 5`. Assert exactly `5` return `reserved = true`, `N - 5` return `reserved = false`, and the table row equals `5`.
  - Launch `N` parallel connections calling `players.fulfil_purchase` for the same `pending` purchase ID. Assert exactly `1` returns `'fulfilled'`, `N - 1` return `'duplicate'`, and `players.accounts.paid_until` increases by one pass period (`30 days`), never `N * 30 days`.
- **Live PostgREST store parity tests (`supabase-py` against local `:54421`):**
  - Run the store contract suite against real `SupabaseScoreStore`, `SupabasePlayerStore`, and `SupabaseSessionStore` (best-score retention, `won`/`mastered` stickiness, `email` exclusion from public listing, `save_board` / `load_board` round-trip, `PurchasePendingError` on `23505`, `move_email`, and `delete_account` anonymisation of `players.purchases`).
  - Isolate each test with unique synthetic identifiers (`dbtest+<uuid>@example.invalid`) and clean up created rows in fixture teardown.

### 3. Developer ergonomics, spec traceability, and CI gate

- `mise run test:api` excludes `-m db` via default pytest configuration so unit tests stay sub-second without Docker.
- `mise run test:db` ensures local Supabase is running (`db:start`), runs `supabase test db`, and runs `uv run pytest apps/api/tests/db -m db`.
- `.github/workflows/ci.yml` (`migrations` job) runs `mise run db:check` followed by `mise run test:db` on every PR touching `supabase/` or `apps/api/tests/db/` and on `main`.
- `scripts/check_spec_coverage.py` supports spec traceability across both Python `@pytest.mark.spec(...)` and pgTAP `-- @spec("...")` annotations if criteria live in SQL files (or all criteria map directly to `@pytest.mark.spec` tests).

## Acceptance criteria

- **API-DB-001**: Given a fresh local Supabase database with all migrations applied, when `anon` or `authenticated` queries or mutates any table in `audit`, `game`, or `players` or executes any function in `players`, then PostgreSQL denies access (`42501` permission denied), and no application tables exist in `public`.
- **API-DB-002**: Given every table in schemas `audit`, `game`, and `players` queried dynamically from `pg_tables` and `pg_class`, then every table has `relrowsecurity = true` and zero privileges granted to `public`, `anon`, or `authenticated`.
- **API-DB-003**: Given `players.purchases`, when a second `pending` row is inserted for the same `(email, livemode)`, then PostgreSQL rejects it with unique violation `23505`; whereas `pending` rows for distinct `livemode` values, multiple `expired`/`paid` rows, and multiple rows with `payment_intent IS NULL` succeed.
- **API-DB-004**: Given `players.reserve_daily_usage` and `players.release_daily_usage`, when invoked for `wave`, `test`, and `train` across boundary limits (`p_limit <= 0`, reaching `p_limit`, invalid `p_kind`, and releasing at `0`), then counts increment atomically up to `p_limit`, refuse above `p_limit`, raise on invalid `p_kind`, and never go below `0`.
- **API-DB-005**: Given `players.fulfil_purchase`, `players.revoke_purchase`, and `players.restore_purchase`, when exercised across `fulfilled`, `duplicate`, `mismatch`, `orphaned`, `no_account`, `unknown`, stacked-pass shifting, and dispute/refund restoration paths, then `paid_until`, `starts_at`, `ends_at`, and `removed` match the exact expected intervals.
- **API-DB-006**: Given `N` concurrent PostgreSQL transactions barrier-synchronized to invoke `players.reserve_daily_usage(..., p_limit => 5)` simultaneously, then exactly `5` calls return `reserved = true` and the stored counter equals `5`; and given `N` concurrent calls to `players.fulfil_purchase` for one purchase, then exactly `1` returns `'fulfilled'` and `paid_until` is extended once.
- **API-DB-007**: Given a running local Supabase stack, when `SupabaseScoreStore`, `SupabasePlayerStore`, and `SupabaseSessionStore` execute their full contract flows (including `PurchasePendingError` on duplicate checkout, `move_email`, and `delete_account` setting `purchases.email = NULL`), then every operation succeeds against real PostgREST with the same observable behaviour as `InMemory*Store`.
- **DEV-DB-001**: Given `apps/api/pyproject.toml` and `mise.toml`, when `mise run test:api` runs without Docker or Supabase, then `@pytest.mark.db` tests are deselected and unit tests pass; when `mise run test:db` runs, then both `supabase test db` (pgTAP) and `pytest -m db` execute and fail on any SQL or integration regression.
- **DEV-DB-002**: Given `.github/workflows/ci.yml`, then the `migrations` job runs `mise run db:check` and `mise run test:db` so CI validates migrations, plpgsql lint, pgTAP, and DB integration tests on database changes and `main`.

## Security & privacy considerations

- **Least-privilege verification:** Dynamically testing `pg_class.relrowsecurity` and role permissions ensures new migrations cannot accidentally expose PII (`players.accounts.email`, `players.sessions.token_hash`, `game.scores.email`, `players.purchases`) via PostgREST.
- **Local-only execution:** `mise run test:db` and `pytest -m db` read only local Supabase configuration (`supabase status -o json` or local test fixtures) and refuse non-local database URLs by default so test data never touches production.
- **Synthetic test data:** All DB fixtures use `.invalid` RFC 2606 domains and synthetic tokens/UUIDs; no real user emails or Stripe secrets are used.

## Evaluation impact

None. No change to `packages/engine` scoring or classifiers.

## Open questions

None.

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: DEV-DB-001, DEV-DB-002
- Red: 2 failing test(s) before implementation (`scripts/tests/test_database_tests.py::test_api_tests_skip_db_tests_and_test_db_runs_them`, `scripts/tests/test_database_tests.py::test_ci_migrations_job_runs_the_database_tests`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
