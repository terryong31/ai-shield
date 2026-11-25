# Persist game data (Supabase)

The gateway stores player accounts and sessions, daily run quotas, saved boards,
the leaderboard and admin console sessions in Supabase (`SUPABASE_URL` and
`SUPABASE_KEY` are required at startup; missing credentials raise
`ConfigurationError` — [spec 0046](../../specs/README.md)):

| Condition | Backend | `GET /api/v1/health` → `storage_backend` |
| --- | --- | --- |
| `SUPABASE_URL` and `SUPABASE_KEY` set | Supabase schemas `audit`, `game`, `players` | `supabase` |

Every table lives in a domain schema; nothing is stored in `public`:

| Schema | Tables |
| --- | --- |
| `audit` | `clearance_sessions` (admin console sessions; token hashes only) |
| `game` | `scores` (leaderboard), `saved_boards` (one board per player and level) |
| `players` | `accounts`, `sessions`, `daily_usage` (run quotas) |

The browser never talks directly to Supabase
([ADR 0004](../explanation/decisions/0004-frontend-talks-only-to-gateway.md)).

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

Local Supabase uses the `5442x` port block (defined in `supabase/config.toml`)
to avoid clashes with other local Supabase projects.

```bash
mise run db:start        # starts Postgres (:54422), API (:54421), Studio (:54423), Mailpit (:54424)
mise run dev             # injects Infisical dev /api + local Supabase env automatically
```

Do not put `SUPABASE_URL` or `SUPABASE_KEY` in `apps/api/.env` or Infisical `dev /api`:
`scripts/local_env.py` reads them from `supabase status -o json` at launch.
`curl localhost:8000/api/v1/health` should report `"storage_backend": "supabase"`.

Studio runs at http://127.0.0.1:54423. `mise run db:status` shows all URLs.
`mise run db:stop` stops the stack and keeps the data; `mise run db:up` applies
pending migrations without wiping data; `mise run db:reset` rebuilds it from
scratch. In Docker Compose (`mise run up`), `scripts/local_env.py --docker`
automatically rewrites `SUPABASE_URL` to `http://host.docker.internal:54421`.

## Use a hosted Supabase project

1. Apply the migrations:

   ```bash
   supabase login                                    # once per machine
   mise run db:link --project-ref <your-project-ref> # once per clone; asks for the database password
   mise run db:remote:status                         # inspect local vs. Cloud migration state
   mise run db:remote:plan                           # dry-run pending migrations
   mise run db:remote:push                           # applies pending migrations only
   ```

2. **Expose the schemas to the Data API.** A hosted project only exposes
   `public` and `graphql_public` until you change it, and `config.toml` does not
   apply to hosted projects. In the dashboard open **Project Settings → Data API**
   (or **API**), add `audit`, `game` and `players` to **Exposed schemas**, and save.
3. Store `SUPABASE_URL` and `SUPABASE_KEY` (the service/secret key) in Infisical
   under `prod` → `/api` and sync to Vercel via Infisical's Vercel integration
   (never in `apps/api/.env` or the web app).

The key is a server-side credential that bypasses RLS. Keep it in your secret
manager. `SUPABASE_ANON_KEY` is still read as a fallback name for older `.env` files.

## Change the schema

Schema changes follow the same spec-driven rules as code: update the owning
spec and add a Supabase migration.

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
| `ConfigurationError: SUPABASE_URL and SUPABASE_KEY are required` | Only one of `SUPABASE_URL` / `SUPABASE_KEY` is set, the names are misspelled (they are case-sensitive), or local Supabase was not started (`mise run db:start` / `mise run infra:up`). |
| `PGRST106 Invalid schema: players` (`Only the following schemas are exposed: public, graphql_public`) | The hosted project does not expose the domain schemas. Add `audit`, `game` and `players` under **Exposed schemas** (step 2 above). |
| `schema "players" does not exist` or `relation … does not exist` | The migrations have not been applied (`mise run db:push` remotely, `mise run db:reset` locally). |
| `permission denied for table …` | The gateway is using the anon/publishable key instead of the service_role/secret key. |
| `db:env` fails with `KeyError` | The auth service was excluded from `supabase start`, so the CLI does not print keys. |
