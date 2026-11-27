# 0056 — Database tests: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Implement a two-layer database test suite wired into `mise.toml` and `.github/workflows/ci.yml`:

1. **pgTAP tests (`supabase/tests/*.sql`):**
   - Enable `pgtap` in local test runs (`CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;` in test preamble or `supabase/tests/00_setup.sql` wrapped cleanly, or via Supabase's built-in pgTAP support in `supabase test db`).
   - Add four focused SQL test files (`01_rls_and_privileges.sql`, `02_constraints_and_indexes.sql`, `03_daily_usage_rpcs.sql`, `04_purchase_rpcs.sql`) running inside `BEGIN ... SELECT * FROM finish(); ROLLBACK;`.
   - Use `SET LOCAL ROLE anon` / `SET LOCAL ROLE authenticated` / `SET LOCAL ROLE service_role` with `throws_ok(..., '42501', ...)` and dynamic `pg_tables` / `pg_proc` introspection so any future table or RPC missing RLS/revokes fails immediately.
2. **Python DB integration & concurrency tests (`apps/api/tests/db/`):**
   - Register custom marker `db: database integration tests requiring local Supabase` in `apps/api/pyproject.toml` and exclude it from default unit runs (`addopts = "--import-mode=importlib --strict-markers -m 'not db'"` or via `mise.toml` `test:api` `-m "not db"` so `pytest apps/api/tests/db -m db` still works directly).
   - Add `psycopg[binary]` as a `dev` dependency in `apps/api/pyproject.toml` (requires user approval before editing dependencies per `AGENTS.md`).
   - Resolve local Supabase URL, `service_role` key, and Postgres DSN (`postgresql://postgres:postgres@127.0.0.1:54422/postgres`) via `supabase status -o json` or explicit `SHIELD_TEST_DB_DSN` / `SHIELD_TEST_SUPABASE_URL` guard that rejects non-loopback hosts unless explicitly permitted.
   - Implement `test_db_concurrency.py` (barrier-synchronized `ThreadPoolExecutor` connections for `reserve_daily_usage` and `fulfil_purchase` race tests) and `test_supabase_stores_live.py` (live `SupabaseScoreStore`, `SupabasePlayerStore`, `SupabaseSessionStore` contract parity and `delete_account`/`move_email` verification).
3. **Tooling & CI (`mise.toml`, `scripts/affected.sh`, `.github/workflows/ci.yml`, `scripts/check_spec_coverage.py`):**
   - Add `test:db` task in `mise.toml`: starts local Supabase if needed, runs `supabase test db`, then runs `uv run pytest apps/api/tests/db -m db`.
   - Ensure `scripts/affected.sh` treats `apps/api/tests/db/**` and `supabase/tests/**` as `ci-database` (and `ci-python` where appropriate).
   - Extend `migrations` job in `.github/workflows/ci.yml` to install Python deps (or run `test:db`) and execute `mise run test:db` after `mise run db:check`.
   - Keep `API-DB-*` and `DEV-DB-*` `@pytest.mark.spec(...)` markers in `apps/api/tests/db/` (and/or teach `scripts/check_spec_coverage.py` to scan `supabase/tests/**/*.sql`) so `mise run spec:check` passes cleanly without needing Docker during static checks.

## Interfaces

No production application HTTP routes, schemas, or `packages/engine` APIs change.

New dev dependency in `apps/api/pyproject.toml` (ask before adding):

- `psycopg[binary]>=3.2` in `[dependency-groups] dev`

New `mise.toml` task:

- `test:db`: runs `supabase test db` and `uv run pytest apps/api/tests/db -m db`

## Boundaries check

- [x] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [x] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New test commands and DB test requirements are documented in `docs/reference/` and `apps/api/README.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Only pgTAP SQL tests (`supabase test db`) | pgTAP runs each file in a single transaction, so it cannot test concurrent multi-connection `FOR UPDATE` locking or real `supabase-py` PostgREST serialization. |
| Only Python `pytest` tests | Slower for exhaustive role/RLS matrix checks and harder to keep inside zero-side-effect `ROLLBACK` transactions per assertion. |
| Ephemeral Testcontainers Postgres instead of `supabase start` | Would diverge from Supabase's `auth`, `anon`/`authenticated`/`service_role` roles, PostgREST schema routing, and `supabase/config.toml`; `supabase start` is already used by `db:check` in CI. |

## Risks and rollback

- **CI duration:** `migrations` job in CI will add Python setup + `supabase test db` + `pytest -m db` (~30–60s). Mitigated by gating `migrations` on `scripts/affected.sh ci-database` for PRs.
- **Accidental remote execution:** Mitigated by failing closed if the target DSN/URL host is not loopback (`127.0.0.1` / `localhost`).
- **Rollback:** Remove `supabase/tests/`, `apps/api/tests/db/`, and revert the `test:db` step in `.github/workflows/ci.yml`.
