# Persist the audit log (SQLite or Supabase)

The gateway stores every screened request in an audit log. Which backend it
uses is decided at startup ([spec 0009](../../specs/0009-audit-log-storage/spec.md)):

| Condition | Backend | `GET /api/v1/health` → `audit_backend` |
| --- | --- | --- |
| `SUPABASE_URL` **and** `SUPABASE_KEY` set in `apps/api/.env` | Supabase table `public.requests` | `supabase` |
| otherwise | SQLite file at `SQLITE_PATH` (default `apps/api/var/shield.db`) | `sqlite` |

SQLite needs no setup, and records survive restarts. Use Supabase when you want
a hosted database, several gateway replicas, or SQL access from Studio.

The browser never talks to either store. It reads the log through
`GET /api/v1/requests` and `GET /api/v1/stats` ([ADR 0004](../explanation/decisions/0004-frontend-talks-only-to-gateway.md)).

## Use SQLite (default)

Do nothing. To move the file, set `SQLITE_PATH=/some/dir/shield.db`. Parent
directories are created. In Docker Compose the file lives in the
`shield-data` volume at `/app/var/shield.db`.

To inspect it: `sqlite3 apps/api/var/shield.db 'select created_at, action, query from requests order by created_at desc limit 10'`.

## The Supabase project in this repo

`supabase/` was created with `supabase init` and is the source of truth for the schema:

```
supabase/
├── config.toml                                   # local stack config (project_id = "ai-shield")
├── migrations/
│   └── 20260922183717_create_requests_table.sql  # public.requests + indexes + RLS
└── seed.sql                                      # demo rows, local only
```

- **Migrations** are applied in filename order, locally by `db:start`/`db:reset`
  and remotely by `db:push`. Never edit a migration that has been pushed; add a new one.
- **`seed.sql`** runs after the migrations on the first `supabase start` and on
  every `supabase db reset` (configured under `[db.seed]` in `config.toml`).
  It never runs on `db push`, so demo rows cannot reach production.
- **RLS** is enabled with no policies for `anon` or `authenticated`, and their
  grants are revoked. Only the server-side key the gateway uses can read or write.

The Supabase CLI is pinned in `mise.toml`, so `mise install` provides it. Docker must be running.

## Use Supabase locally

```bash
mise run db:start        # starts Postgres, API gateway, Studio…; applies migrations + seed
mise run db:env          # prints SUPABASE_URL=… and SUPABASE_KEY=… (service_role)
```

Paste the two lines into `apps/api/.env`, then restart the API (`mise run api:dev`).
`curl localhost:8000/api/v1/health` should now report `"audit_backend": "supabase"`,
and the dashboard shows the five seed rows.

Studio runs at http://127.0.0.1:54323. `mise run db:status` shows all URLs.
`mise run db:stop` stops the stack and keeps the data; `mise run db:reset`
rebuilds it from migrations and seed.

If the API runs in Docker Compose instead, use
`SUPABASE_URL=http://host.docker.internal:54321`.

## Change the schema

Schema changes follow the same spec-driven rules as code: update spec 0009,
and keep the SQLite schema in `services/audit.py` in sync. The test for
API-STORE-006 fails if the two drift.

```bash
mise run db:migration add_request_tags   # creates supabase/migrations/<timestamp>_add_request_tags.sql
# write the SQL, then:
mise run db:reset                        # re-applies all migrations + seed locally
mise run db:lint                         # checks the schema
```

If you prototyped the change in Studio, generate the migration from the difference instead:
`mise run db:diff -f add_request_tags`.

## Deploy to a hosted Supabase project

```bash
supabase login                                    # once per machine
mise run db:link --project-ref <your-project-ref> # once per clone
mise run db:push                                  # applies pending migrations only
```

Then set these on the gateway (never in the web app):

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<service_role or secret key>
```

The key is a server-side credential that bypasses RLS. Keep it in your secret
manager. `SUPABASE_ANON_KEY` is still read as a fallback name for older `.env` files.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `audit_backend` is `sqlite` although Supabase is configured | Only one of `SUPABASE_URL` / `SUPABASE_KEY` is set (API-STORE-004). |
| Dashboard shows HTTP 500 on `/requests` | Supabase is unreachable. Writes are logged and skipped, but reads fail loudly. |
| `permission denied for table requests` | The gateway is using the anon/publishable key. Use the service_role/secret key. |
| `db:env` fails with `KeyError` | The auth service was excluded from `supabase start`, so the CLI does not print keys. |
