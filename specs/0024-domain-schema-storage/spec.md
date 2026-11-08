# 0024 — Domain-scoped database schemas (`audit`, `game`, `players`)

- **Status:** Implemented
- **Area:** API
- **Owner:** Terry Ong
- **Created:** 2026-11-08
- **Related:** [spec 0009](../0009-audit-log-storage/spec.md) (audit log storage), [spec 0012](../0012-clearance-sessions/spec.md) (clearance sessions), [spec 0016](../0016-game-engine/spec.md) (game API and player auth), [spec 0020](../0020-game-ai-agent/spec.md) (run quotas), [spec 0021](../0021-game-level-tiers/spec.md) (`score_version`), [spec 0023](../0023-game-saved-boards/spec.md) (saved boards), [plan.md](plan.md), [tasks.md](tasks.md)

## Problem

Today the database layout has three structural flaws:

1. **Everything in `public`:** In PostgreSQL / Supabase, `public.requests` lives in the default `public` schema, which Supabase exposes by default and shares with extensions and system defaults.
2. **Half-migrated domains:** Game leaderboard scores (`scores`), saved boards (`player_saved_boards`), player accounts/sessions/quotas (`player_accounts`, `player_sessions`, `player_daily_usage`), and admin clearance sessions (`sessions`) exist only in local SQLite or in-memory lists (`SupabaseAuditLog._scores` is an in-memory list!). There are no PostgreSQL migrations or Supabase stores for `game` or `players`, so when Supabase is configured in production, leaderboard scores, player accounts, and sessions do not persist in PostgreSQL at all.
3. **No domain boundaries:** Tables across three distinct bounded contexts (gateway security & audit, game progression & leaderboard, and player identity & quotas) sit in a single flat namespace with inconsistent prefixes.

## Goals

- **No application tables in `public`:** Move all PostgreSQL tables out of `public` into dedicated, domain-scoped schemas following PostgreSQL and Supabase best practices:
  - `audit` — gateway screening audit log and admin clearance sessions (`audit.requests`, `audit.clearance_sessions`).
  - `game` — game leaderboard scores and saved boards (`game.scores`, `game.saved_boards`).
  - `players` — player accounts, sessions, and daily usage quotas (`players.accounts`, `players.sessions`, `players.daily_usage`).
- **Full PostgreSQL / Supabase persistence across all domains:** Implement `SupabaseSessionStore` and `SupabasePlayerStore`, and persist `game.scores` in `SupabaseAuditLog` (or a dedicated game store) against the `game` schema instead of an in-memory list, so configuring `SUPABASE_URL` and `SUPABASE_KEY` persists every domain in PostgreSQL.
- **Matching domain-isolated SQLite fallback:** In SQLite (for zero-setup local dev and offline tests), attach per-domain database files (`audit`, `game`, `players`) or use the exact `<schema>.<table>` qualified names via `ATTACH DATABASE` so SQLite queries and schema checks mirror PostgreSQL's `audit.*`, `game.*`, and `players.*` layout 1-to-1.
- **Least-privilege security on every schema:** Enable Row Level Security (RLS) on every table in `audit`, `game`, and `players`, revoke all privileges from `anon` and `authenticated`, and grant access only to `service_role` (ADR 0004: the browser never talks to Supabase directly).

## Non-goals

- Exposing database tables directly to the browser via PostgREST (`anon` / `authenticated`). All access continues to go through the FastAPI gateway (`apps/api`) using the server-side `service_role` key.
- Migrating existing local `var/shield.db` data automatically (local dev databases can be recreated, and `supabase db reset` rebuilds local Postgres).
- Changing any engine (`packages/engine`) or web (`apps/web`) behaviour or HTTP contract shapes.

## Behaviour

### Domain schemas and tables

No application tables remain in `public`. Each bounded context owns its own PostgreSQL schema:

| Schema | Table | Primary Key | Purpose |
| --- | --- | --- | --- |
| `audit` | `audit.requests` | `id uuid` | Screened prompt audit log (`created_at`, `query`, `action`, `reason`, `layer`, `metadata`, `reviewed`, `human_label`) |
| `audit` | `audit.clearance_sessions` | `token_hash text` | Admin console clearance sessions (`created_at`, `expires_at`) |
| `game` | `game.scores` | `id uuid` | Leaderboard high scores (`created_at`, `player_name`, `level_id`, `total_score`, `medal`, `attacks_blocked`, `attacks_total`, `false_alarms`, `avg_latency_ms`, `total_cost_usd`, `board_json`, `score_version`) |
| `game` | `game.saved_boards` | `(email, level_id)` | Player saved boards per level (`email`, `level_id`, `save_json`, `updated_at`) |
| `players` | `players.accounts` | `email text` | Registered player accounts (`email`, `password_hash`, `salt`, `player_name`, `tier`, `created_at`) |
| `players` | `players.sessions` | `token_hash text` | Player auth & anonymous sessions (`token_hash`, `email`, `is_anonymous`, `player_name`, `tier`, `created_at`, `expires_at`) |
| `players` | `players.daily_usage` | `(email, usage_date)` | Daily wave and custom test run counters (`email`, `usage_date`, `wave_runs`, `test_runs`) |

### Supabase configuration (`supabase/config.toml`)

- `[api].schemas` exposes `["audit", "game", "players"]` to PostgREST for the gateway's `service_role` client, removing `"public"`.
- `supabase/migrations/` defines the `audit`, `game`, and `players` schemas, moves/creates all seven tables in their respective schemas, drops `public.requests`, enables RLS on every table, revokes all privileges on those schemas/tables from `anon` and `authenticated`, and grants usage and table privileges to `service_role`.
- `supabase/seed.sql` seeds demo rows into `audit.requests`.

### Gateway persistence adapters (`apps/api`)

When `SUPABASE_URL` and `SUPABASE_KEY` are both configured in `Settings`:

| Container service | Supabase adapter | Schema & tables used |
| --- | --- | --- |
| `container.audit_log` | `SupabaseAuditLog` | `audit.requests`, `game.scores` |
| `container.sessions` | `SupabaseSessionStore` | `audit.clearance_sessions` |
| `container.players` | `SupabasePlayerStore` | `players.accounts`, `players.sessions`, `players.daily_usage`, `game.saved_boards` |

When `SUPABASE_URL` or `SUPABASE_KEY` is unset (offline / zero-setup local mode):

- `SqliteAuditLog`, `SqliteSessionStore`, and `SqlitePlayerStore` attach domain schemas (`audit`, `game`, `players`) on each SQLite connection and qualify every SQL statement with `<schema>.<table>` (`audit.requests`, `audit.clearance_sessions`, `game.scores`, `game.saved_boards`, `players.accounts`, `players.sessions`, `players.daily_usage`), with zero tables created in SQLite's default `main` schema.

## Acceptance criteria

- **API-SCHEMA-001**: Given the Supabase migrations in `supabase/migrations/`, when inspected or applied, then schemas `audit`, `game`, and `players` are created, `public` contains no application tables (`public.requests` is dropped or moved), and all domain tables (`audit.requests`, `audit.clearance_sessions`, `game.scores`, `game.saved_boards`, `players.accounts`, `players.sessions`, `players.daily_usage`) have RLS enabled with privileges revoked from `anon` and `authenticated` and granted to `service_role`.
- **API-SCHEMA-002**: Given `supabase/config.toml` and `supabase/seed.sql`, when inspected, then `[api].schemas` lists `"audit"`, `"game"`, and `"players"` (not `"public"`), and `seed.sql` inserts demo rows into `audit.requests`.
- **API-SCHEMA-003**: Given `SupabaseAuditLog`, when `record`, `recent`, `stats`, `review`, `record_score`, `list_scores`, and `clear_scores` are called, then audit operations query ` client.schema("audit").table("requests")` and leaderboard score operations query `client.schema("game").table("scores")` (persisting scores in Supabase rather than in memory).
- **API-SCHEMA-004**: Given `SupabaseSessionStore` and `SupabasePlayerStore`, when clearance session or player account/session/quota operations run, then `SupabaseSessionStore` queries `client.schema("audit").table("clearance_sessions")` and `SupabasePlayerStore` queries `client.schema("players").table("accounts" | "sessions" | "daily_usage")`, satisfying the exact behavioural contracts of `SessionStore` and `PlayerStore`.
- **API-SCHEMA-005**: Given both `SUPABASE_URL` and `SUPABASE_KEY` in `Settings`, when `build_container` runs, then `container.audit_log`, `container.sessions`, and `container.players` are all wired to their `Supabase*` implementations; when either setting is missing, all three fall back to their `Sqlite*` implementations.
- **API-SCHEMA-006**: Given `SqliteAuditLog`, `SqliteSessionStore`, and `SqlitePlayerStore`, when initialized, then they attach domain schemas (`audit`, `game`, `players`), create no tables in `main`, and the columns of every SQLite table match the columns of the corresponding `<schema>.<table>` in `supabase/migrations/`. (Supersedes API-STORE-006.)

## Security & privacy considerations

- **Defense in depth against accidental PostgREST exposure:** Leaving tables in `public` means any table created without explicit `REVOKE` / `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` is immediately reachable over Supabase's Data API with an `anon` key (`auto_expose_new_tables = true`). Moving all tables into custom schemas (`audit`, `game`, `players`) with explicit `GRANT USAGE ON SCHEMA <schema> TO service_role` and `REVOKE ALL ON SCHEMA <schema> FROM public, anon, authenticated` ensures `anon` and `authenticated` roles cannot even resolve the schemas.
- **Gateway remains the sole database client:** In accordance with ADR 0004, `apps/web` never talks to Supabase directly.
- **Token and password hashing unchanged:** `audit.clearance_sessions` and `players.sessions` continue to store only SHA-256 token hashes; `players.accounts` stores PBKDF2-HMAC-SHA256 password hashes and per-account salts.

## Evaluation impact

None. `packages/engine` is untouched.

## Open questions

None.

## Verification

_Filled in by `mise run sdd:done`._

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: API-SCHEMA-001, API-SCHEMA-002, API-SCHEMA-003, API-SCHEMA-004, API-SCHEMA-005, API-SCHEMA-006
- Red: 6 failing test(s) before implementation (`apps/api/tests/test_domain_schemas.py`, `apps/api/tests/test_domain_schemas.py`, `apps/api/tests/test_domain_schemas.py`)
- Green: 6 passing test(s)
- Gate: `mise run check` passed
