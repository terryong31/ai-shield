# 0024 — Domain-scoped database schemas (`audit`, `game`, `players`): implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **PostgreSQL migrations & Supabase config (`supabase/`):**
   - Add a new migration `supabase/migrations/<timestamp>_domain_schemas.sql` that:
     - Creates schemas `audit`, `game`, and `players`.
     - Moves `public.requests` to `audit.requests` (`alter table public.requests set schema audit;`).
     - Creates `audit.clearance_sessions`, `game.scores`, `game.saved_boards`, `players.accounts`, `players.sessions`, and `players.daily_usage` with appropriate primary keys, constraints, and indexes.
     - Enables RLS on every table and revokes all access on schemas `audit`, `game`, `players` and their tables from `public`, `anon`, and `authenticated`, granting usage and all privileges on tables to `service_role`.
   - Update `supabase/seed.sql` to insert into `audit.requests`.
   - Update `supabase/config.toml` so `[api].schemas = ["audit", "game", "players", "graphql_public"]` and `extra_search_path = ["extensions"]`, and update `mise.toml` `db:diff` / `db:lint` tasks to check `--schema audit,game,players`.

2. **Supabase adapters (`apps/api/src/shield_api/services/`):**
   - `SupabaseAuditLog` (`services/audit.py`):
     - Use `self._client.schema("audit").table("requests")` for audit records.
     - Use `self._client.schema("game").table("scores")` for `record_score`, `list_scores`, and `clear_scores` instead of the in-memory `self._scores` list.
   - `SupabaseSessionStore` (`services/sessions.py`):
     - Implement `SessionStore` against `self._client.schema("audit").table("clearance_sessions")`.
   - `SupabasePlayerStore` (`services/players.py`):
     - Implement `PlayerStore` against `self._client.schema("players").table("accounts")`, `table("sessions")`, and `table("daily_usage")` (plus `self._client.schema("game").table("saved_boards")` when spec 0023 lands).
   - `build_container` (`container.py`):
     - When `SUPABASE_URL` and `SUPABASE_KEY` are set, instantiate a single Supabase client and wire `SupabaseAuditLog(client)`, `SupabaseSessionStore(client)`, and `SupabasePlayerStore(client)`.

3. **SQLite multi-schema parity (`Sqlite*` stores):**
   - SQLite supports `ATTACH DATABASE '<path>' AS <schema>`. By attaching `<stem>.audit.db AS audit`, `<stem>.game.db AS game`, and `<stem>.players.db AS players` (or using a helper in a shared `shield_api/services/sqlite.py`), every SQL query in `SqliteAuditLog`, `SqliteSessionStore`, and `SqlitePlayerStore` uses the exact qualified table names (`audit.requests`, `audit.clearance_sessions`, `game.scores`, `players.accounts`, `players.sessions`, `players.daily_usage`), and `main` stays completely empty.
   - Update the schema-mirroring test (`API-SCHEMA-006`) to verify that every table across `audit`, `game`, and `players` in the Supabase migrations matches the columns in SQLite (`pragma <schema>.table_info(<table>)`).

## Interfaces

```python
# apps/api/src/shield_api/services/sessions.py
class SupabaseSessionStore:
    SCHEMA = "audit"
    TABLE = "clearance_sessions"
    def __init__(self, client: Any) -> None: ...
    async def create(self, ttl: timedelta) -> tuple[str, datetime]: ...
    async def lookup(self, token: str) -> datetime | None: ...
    async def revoke(self, token: str) -> None: ...

# apps/api/src/shield_api/services/players.py
class SupabasePlayerStore:
    SCHEMA = "players"
    ACCOUNTS_TABLE = "accounts"
    SESSIONS_TABLE = "sessions"
    USAGE_TABLE = "daily_usage"
    def __init__(self, client: Any) -> None: ...
    # implements PlayerStore protocol
```

No HTTP routes or OpenAPI schemas change.

## Boundaries check

- [x] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [x] `apps/web` still talks to the backend only through the published OpenAPI contract
- [x] New configuration is documented in `docs/reference/configuration.md` and `docs/how-to/persist-the-audit-log.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep everything in `public` with table prefixes (`audit_requests`, `game_scores`, `players_accounts`) | Does not isolate permissions or search paths at the PostgreSQL schema level; leaves tables in the default `public` schema exposed by PostgREST unless individually locked down. |
| Separate schemas per single table (e.g. 7 schemas) | Over-fragmented; grouping by bounded context (`audit`, `game`, `players`) is the standard DDD / PostgreSQL practice and keeps related tables (like `players.accounts`, `players.sessions`, `players.daily_usage`) together for foreign keys and grants. |
| Remove SQLite completely and require Docker / Supabase for `pytest` | Violates the repository rule "No network in tests" and breaks zero-setup offline runs (`mise run test`). Keeping `Sqlite*` with `ATTACH DATABASE ... AS <schema>` and `FakeClient.schema(...)` in tests preserves 100% offline test execution while giving full Supabase Postgres persistence for every domain. |

## Risks and rollback

- **Risk:** Existing local Supabase containers have data in `public.requests`.
  - **Mitigation:** The migration uses `alter table if exists public.requests set schema audit;` so existing rows in `public.requests` are preserved and moved cleanly into `audit.requests`.
- **Rollback:** Revert the migration and `container.py` wiring.
