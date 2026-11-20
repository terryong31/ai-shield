# Persist game data (SQLite or Supabase)

The gateway stores player accounts and sessions, daily run quotas, saved boards,
the leaderboard and admin console sessions. Which backend it uses is decided at
startup ([spec 0024](../../specs/0024-domain-schema-storage/spec.md)):

| Condition | Backend | `GET /api/v1/health` → `storage_backend` |
| --- | --- | --- |
| `SUPABASE_URL` **and** `SUPABASE_KEY` set in `apps/api/.env` | Supabase schemas `audit`, `game`, `players` | `supabase` |
| otherwise | SQLite domain files beside `SQLITE_PATH` (default `apps/api/var/shield.db`) | `sqlite` |

Every table lives in a domain schema; nothing is stored in `public`:

| Schema | Tables |
| --- | --- |
| `audit` | `clearance_sessions` (admin console sessions; token hashes only) |
| `game` | `scores` (leaderboard), `saved_boards` (one board per player and level) |
| `players` | `accounts`, `sessions`, `daily_usage` (run quotas) |

SQLite needs no setup, and data survives restarts. Use Supabase when you want a
hosted database, several gateway replicas, or SQL access from Studio. The
browser never talks to either store ([ADR 0004](../explanation/decisions/0004-frontend-talks-only-to-gateway.md)).

## Use SQLite (default)

Do nothing. Each schema is its own SQLite file next to `SQLITE_PATH`, attached
under the schema's name, so queries read `game.scores` exactly as in Postgres:
`var/shield.audit.db`, `var/shield.game.db` and `var/shield.players.db`
(`var/shield.db` itself stays empty). To move them, set
`SQLITE_PATH=/some/dir/shield.db`. In Docker Compose the files live in the
`shield-data` volume under `/app/var/`.

To start over, stop the API and run `mise run local:db:reset` (it asks first,
then deletes those files and their journals). The next start creates empty
databases.

To inspect: `sqlite3 apps/api/var/shield.game.db 'select player_name, level_id, total_score from scores order by total_score desc limit 10'`.

## The Supabase project in this repo

`supabase/` is the source of truth for the schema:

```
supabase/
├── config.toml                                   # local stack config (project_id = "ai-shield")
├── migrations/
│   ├── 20260922183717_create_requests_table.sql  # the original request log (later dropped)
│   ├── 20261108120000_domain_schemas.sql         # audit, game, players schemas and tables
│   └── 20261108213955_drop_audit_requests.sql    # drops the chat request log (spec 0026)
└── seed.sql                                      # local only; the game needs no seed rows
```

- **Migrations** are applied in filename order, locally by `db:start`/`db:reset`
  and remotely by `db:push`. Never edit a migration that has been pushed; add a new one.
- **RLS** is enabled on every table with no policies for `anon` or `authenticated`,
  and their grants are revoked. Only the server-side key the gateway uses can
  read or write. `config.toml` exposes only `audit`, `game` and `players` to the
  Data API, not `public`.

The Supabase CLI is pinned in `mise.toml`, so `mise install` provides it. Docker must be running.

## Use Supabase locally

```bash
mise run db:start        # starts Postgres, the API gateway, Studio…; applies migrations
mise run db:env          # prints SUPABASE_URL=… and SUPABASE_KEY=… (service_role)
```

Paste the two lines into `apps/api/.env`, then restart the API (`mise run api:dev`).
`curl localhost:8000/api/v1/health` should now report `"storage_backend": "supabase"`.

Studio runs at http://127.0.0.1:54323. `mise run db:status` shows all URLs.
`mise run db:stop` stops the stack and keeps the data; `mise run db:reset`
rebuilds it from the migrations. If the API runs in Docker Compose instead, use
`SUPABASE_URL=http://host.docker.internal:54321`.

## Use a hosted Supabase project

1. Apply the migrations:

   ```bash
   supabase login                                    # once per machine
   mise run db:link --project-ref <your-project-ref> # once per clone; asks for the database password
   mise run db:push                                  # applies pending migrations only
   ```

2. **Expose the schemas to the Data API.** A hosted project only exposes
   `public` and `graphql_public` until you change it, and `config.toml` does not
   apply to hosted projects. In the dashboard open **Project Settings → Data API**
   (or **API**), add `audit`, `game` and `players` to **Exposed schemas**, and save.
3. Set these on the gateway (never in the web app), then restart it:

   ```env
   SUPABASE_URL=https://<project-ref>.supabase.co
   SUPABASE_KEY=<service_role or secret key>
   ```

The key is a server-side credential that bypasses RLS. Keep it in your secret
manager. `SUPABASE_ANON_KEY` is still read as a fallback name for older `.env` files.

## Change the schema

Schema changes follow the same spec-driven rules as code: update the owning
spec, and keep the SQLite tables in `services/scores.py`, `services/sessions.py`
and `services/players.py` in sync. The test for API-SCHEMA-006 fails if any
table drifts from the migrations.

```bash
mise run db:migration add_score_email   # creates supabase/migrations/<timestamp>_add_score_email.sql
# write the SQL, then:
mise run db:reset                       # re-applies all migrations locally
mise run db:lint                        # checks the schema
```

If you prototyped the change in Studio, generate the migration from the
difference instead: `mise run db:diff -f add_score_email`.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `storage_backend` is `sqlite` although Supabase is configured | Only one of `SUPABASE_URL` / `SUPABASE_KEY` is set, the names are misspelled (they are case-sensitive), or the file is not exactly `apps/api/.env`. |
| `PGRST106 Invalid schema: players` (`Only the following schemas are exposed: public, graphql_public`) | The hosted project does not expose the domain schemas. Add `audit`, `game` and `players` under **Exposed schemas** (step 2 above). |
| `schema "players" does not exist` or `relation … does not exist` | The migrations have not been applied (`mise run db:push` remotely, `mise run db:reset` locally). |
| `permission denied for table …` | The gateway is using the anon/publishable key instead of the service_role/secret key. |
| `db:env` fails with `KeyError` | The auth service was excluded from `supabase start`, so the CLI does not print keys. |
