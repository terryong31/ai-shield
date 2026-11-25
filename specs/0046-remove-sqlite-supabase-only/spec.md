# 0046 — Remove SQLite: Supabase is the only store

- **Status:** Implemented
- **Area:** API | DEV
- **Owner:** Terry Ong
- **Created:** 2026-11-24
- **Related:** [0024-domain-schema-storage](../0024-domain-schema-storage/spec.md), [0027-player-email-confirmation](../0027-player-email-confirmation/spec.md), [0042](../0042-run-spend-and-account-integrity/spec.md), [0043](../0043-rate-limiting-and-client-ip/spec.md) (API-PROD-*), [0044](../0044-leaderboard-read-scaling/spec.md), [0045](../0045-train-upload-hardening/spec.md)

## Problem

The gateway has two storage backends and two identity paths, chosen by whether
`SUPABASE_URL` and `SUPABASE_KEY` are both set (`container.py` `build_container`):

- **SQLite** (`SqliteScoreStore`, `SqlitePlayerStore`, `SqliteSessionStore`,
  `services/sqlite.py` `connect_domains`, setting `SQLITE_PATH`, task
  `mise run local:db:reset`) when Supabase is not configured.
- **A local identity path**: PBKDF2 password hashing (`_hash_password`,
  `_password_matches` in `services/players.py`), and local register / login /
  password check / password change in `routers/auth.py` and
  `routers/account.py`, used whenever `container.identity is None`.

Production is Vercel + Supabase, where SQLite cannot work (ephemeral disk) and
the local identity path is never used. Keeping both doubles the code, the
tests, the migrations that must be mirrored (AGENTS.md: "Mirror column changes
in `SqliteAuditLog` (API-STORE-006)"), and the behaviour that differs between
development and production (for example email change, spec 0042).

## Goals

- Supabase (local stack in development, hosted in production) is the only
  persistent store and the only identity provider outside tests.
- One code path for identity: `SupabasePlayerIdentity`.
- Tests stay hermetic: in-memory stores and the fake Supabase client, never a
  real Supabase or the network.

## Non-goals

- Making Redis required in development (stays production-only, spec 0043;
  in-memory fallbacks stay for development).
- Changing Supabase schemas other than dropping the unused local password columns.
- Changing any HTTP behaviour beyond what the removal of local mode implies.

## Behaviour

### Configuration

`build_container` raises `ConfigurationError` in **every** environment when
`SUPABASE_URL` or `SUPABASE_KEY` is missing or blank, after one error log line
naming the missing settings. `REDIS_URL` stays required only with
`APP_ENV=production` (spec 0043, API-PROD-002); development keeps the
in-memory fallbacks for Redis-backed features.

`SQLITE_PATH` is removed from `Settings` (an old `.env` that still sets it is
ignored, as pydantic-settings ignores unknown keys in this project).

### Removed code

| Removed | Where |
| --- | --- |
| `SqliteScoreStore` | `services/scores.py` |
| `SqlitePlayerStore` | `services/players.py` |
| `SqliteSessionStore` | `services/sessions.py` |
| `connect_domains` and the module | `services/sqlite.py` |
| `SqliteAuditLog` | already removed by spec 0026; only the AGENTS.md rule remains |
| `SQLITE_PATH` | `settings.py`, `.env.example`, docs |
| `mise run local:db:reset` | `mise.toml` (the existing `mise run db:reset` = `supabase db reset` replaces it) |
| `_hash_password`, `_password_matches`, `PlayerAlreadyExistsError`, `InvalidCredentialsError` | `services/players.py` |
| `PlayerStore.register`, `.login`, `.verify_password`, `.set_password` (and their implementations in the in-memory and Supabase stores) | `services/players.py` |
| Local branches (`if container.identity is not None: … else: …`) | `routers/auth.py` register and login; `routers/account.py` `_reauthenticate`, change password, change email, delete account |
| Inline `create_client` in `POST /auth/recover` | `routers/auth.py`; replaced by `container.identity.recover(email)` (wiring stays in `container.py`) |
| `NoAdminAuthenticator` | `services/admins.py`; `SupabaseAdminAuthenticator` is always used |
| `"sqlite"` in `HealthResponse.storage_backend` | `schemas.py` (now `"supabase" \| "memory"`) |

`Container.identity` becomes a required `PlayerIdentity` (no `None`), and
`Container.admins` has no default.

### Supabase migration

A new migration drops `players.accounts.password_hash` and `players.accounts.salt`
(nullable since API-VERIFY-009, unused once local mode is gone).

### Local infrastructure (dev and Docker)

Local development uses the **local Supabase stack**; production uses Supabase
Cloud. Redis runs locally from `compose.yaml` (always on, not a profile) for
parity with Upstash.

**`mise run dev`** (API on :8000, web on :3000) brings the infrastructure up
first, with no manual env copying:

1. New task `infra:up`: `supabase start` only if `supabase status` reports the
   stack is not running (idempotent), then `docker compose up -d redis --wait`
   (the existing `redis:start`). It fails with a clear message if Docker is not
   running.
2. `api:dev` depends on `infra:up` and starts uvicorn through a small launcher
   (`scripts/local_env.py`) that reads `supabase status -o json` and sets
   `SUPABASE_URL` (`API_URL`) and `SUPABASE_KEY` (`SERVICE_ROLE_KEY`, else
   `SECRET_KEY`) in the API process environment, plus
   `REDIS_URL=redis://localhost:6379/0`. Values already set in the environment
   or in `apps/api/.env` win (so a developer can point at a cloud project); the
   launcher never writes `.env` files and never prints the key.
3. `web:dev` starts as today. `dev` depends on `api:dev` and `web:dev`.

**`mise run up`** (full Docker, for anyone trying the project, e.g. a
recruiter): `mise install && mise run setup && mise run up` is all it takes
with Docker and mise installed.

1. `up` depends on `db:start` (idempotent as above).
2. It runs `docker compose up --build` with `SUPABASE_URL` rewritten for
   containers (`127.0.0.1` / `localhost` → `host.docker.internal`, e.g.
   `http://host.docker.internal:54321`) and `SUPABASE_KEY` from
   `supabase status`, passed as environment variables to Compose (the same
   launcher, `scripts/local_env.py --docker`), never written to disk.
3. Compose starts `redis`, `api` (reaching Supabase through the existing
   `extra_hosts: host.docker.internal:host-gateway`, with
   `REDIS_URL=redis://redis:6379/0`) and `web`.

**Tooling.** The Supabase CLI is already a mise-managed tool
(`[tools] supabase = "2.116.0"` in `mise.toml`), so `mise install` installs it;
`mise run setup` gains a first step `mise install` so one command installs every
tool and dependency. No new tool is added. Docker is a prerequisite (not
mise-managed).

- `mise run db:reset` (`supabase db reset`) is the reset command.
- `supabase/config.toml` keeps `enable_confirmations = false` for local use.

### Tests

Tests never need Supabase or the network. They keep building a `Container`
directly with `InMemoryScoreStore`, `InMemoryPlayerStore`,
`InMemorySessionStore`, and with `SupabasePlayerIdentity` /
`SupabaseAdminAuthenticator` over the existing in-process fake auth client
(`conftest.py` `FakeAuthDirectory`, `FakeClient`). The shared harness defaults
to that fake identity (today `supabase_players=False` selects the local path;
that option is removed).

## Acceptance criteria

- **API-SUPA-001**: Given `SUPABASE_URL` or `SUPABASE_KEY` unset or blank, in `APP_ENV="development"` and in `"production"`, when `build_container` runs, then it raises `ConfigurationError`, one error log record names the missing settings and mentions `mise run db:start`, and no file is created under the working directory.
- **API-SUPA-002**: Given `APP_ENV="development"`, Supabase set (fake client factory, no network) and no `REDIS_URL`, when `build_container` runs, then it succeeds with `SupabaseScoreStore`, `SupabasePlayerStore`, `SupabaseSessionStore`, `SupabasePlayerIdentity` and `SupabaseAdminAuthenticator`, and the Redis-backed features use their in-memory fallbacks.
- **API-SUPA-003**: Given the `shield_api` package, then no module defines or imports `SqliteScoreStore`, `SqlitePlayerStore`, `SqliteSessionStore`, `connect_domains`, `sqlite3`, `_hash_password`, `_password_matches` or `NoAdminAuthenticator`, and `Settings` has no `SQLITE_PATH` field.
- **API-SUPA-004**: Given `PlayerStore`, then it has no `register`, `login`, `verify_password` or `set_password` method, and `Container` requires `identity` (constructing it without one is a type error under mypy and a `TypeError` at runtime).
- **API-SUPA-005**: Given `POST /auth/register`, `POST /auth/login`, `POST /account/password`, `POST /account/email` and `DELETE /account`, when called through the harness, then every password check and change goes through the fake Supabase auth client (the fake records the calls) and the player store is never asked to hash or compare a password.
- **API-SUPA-006**: Given `POST /auth/recover`, then it calls `container.identity.recover(email)` exactly once (fake identity records it) and answers the same body for known and unknown addresses; the router module does not import `supabase`.
- **API-SUPA-007**: Given `GET /health`, then `storage_backend` is `"supabase"` for a Supabase container and `"memory"` for the in-memory test container, and the contract's enum is exactly `["supabase", "memory"]`.
- **API-SUPA-008**: Given the migrations in `supabase/migrations/`, then the newest player-schema migration drops `password_hash` and `salt` from `players.accounts`, and the fake Supabase player store no longer reads or writes them.
- **DEV-SUPA-001**: Given `mise.toml` (parsed with `tomllib` in a `scripts/tests/` test), then there is no `local:db:reset` task, `db:reset` runs `supabase db reset`, `[tools]` pins `supabase`, `setup` runs `mise install` before `uv sync` and `bun install`, `infra:up` exists, `api:dev` depends on `infra:up`, `dev` depends on `api:dev` and `web:dev`, and `up` depends on `db:start`.
- **DEV-SUPA-002**: Given `compose.yaml` (parsed as YAML), then services `redis`, `api` and `web` exist, `redis` has no `profiles` key (always on), `api` has `extra_hosts` with `host.docker.internal:host-gateway`, `REDIS_URL` defaulting to `redis://redis:6379/0`, takes `SUPABASE_URL` and `SUPABASE_KEY` from the environment, and has no volume; the file defines no top-level `volumes`.
- **DEV-SUPA-003**: Given `local_supabase_env(status_json, existing_env)` (pure, in `scripts/local_env.py`) and a captured `supabase status -o json` sample, then it returns `SUPABASE_URL` = `API_URL`, `SUPABASE_KEY` = `SERVICE_ROLE_KEY` (or `SECRET_KEY` when that is absent) and `REDIS_URL=redis://localhost:6379/0`; keys already present in `existing_env` are kept unchanged; malformed or missing JSON raises an error whose message says to run `mise run db:start`.
- **DEV-SUPA-004**: Given `docker_supabase_url(url)`, then `http://127.0.0.1:54321` and `http://localhost:54321` become `http://host.docker.internal:54321`, and any other host is returned unchanged.
- **DEV-SUPA-005**: Given the launcher in `--docker` mode with a fake `supabase status` output, then the environment it passes to `docker compose` holds the rewritten `SUPABASE_URL` and the key, nothing is written to any file, and the key never appears in captured stdout/stderr.
- **DEV-SUPA-006**: Given the repository, when `scripts/tests/test_no_sqlite.py` scans every tracked file with a case-insensitive search for the word, then matches occur only in the five exception paths listed under *Sunset* (pushed migrations, `CHANGELOG.md`, `specs/` and `docs/explanation/decisions/`, `bun.lock`, and the test file itself); and no criterion line of an `Accepted` or `Implemented` spec contains the word.
- **ENG-SUPA-001**: Given campaign message `e4_2` from `get_level`, then its text is exactly "Why do the Postgres docs mention SELECT * FROM pg_catalog.pg_tables in read-only tests?", it is still a benign message (`is_attack` False, category `normal`), and no level message text in the engine contains the word "sqlite" (case-insensitive).

### Sunset: nothing SQLite-related remains

After this spec, `rg -i sqlite` over the repository (excluding `.git`,
`node_modules`, `.venv` and build output) returns matches **only** in:

1. **Pushed migrations** in `supabase/migrations/` (never edited; today
   `20261108120000_domain_schemas.sql`).
2. **`CHANGELOG.md`** historical entries, including this change's `### Removed`
   line.
3. **Historical records**: `specs/` (spec documents keep their history; the
   criteria of Accepted and Implemented specs must not mention it, see
   DEV-SUPA-006) and `docs/explanation/decisions/` (ADRs are records of past
   decisions and are not rewritten).
4. **`bun.lock`**: third-party package metadata. `db0` is a hard dependency of
   `nitropack` and `unstorage` (Nuxt's server engine) and *lists* SQLite
   drivers as optional peers; none is installed and nothing here uses them.
   The lockfile is generated, so it cannot be edited by hand.
5. **The sunset test itself** (`scripts/tests/test_no_sqlite.py`), which must
   name the word to search for it.

The benign campaign message `e4_2` (a technical question that looks like SQL,
used to test false alarms) is reworded to its Postgres equivalent
(ENG-SUPA-001). It is plain text classified by the player's board; nothing
executes it and no database is involved, so no table or worker is needed.

Everything else is changed: code, `settings.py`, `apps/api/Dockerfile`
(`SQLITE_PATH` env), `.env.example`, `compose.yaml` (volume `shield-data`),
`mise.toml` (`local:db:reset`), `AGENTS.md`, `apps/api/AGENTS.md`,
`apps/api/README.md`, `README.md`, the `docs/` tree (outside ADRs),
`.claude/skills/tdd/SKILL.md` (the "mirror the columns in `SqliteAuditLog`"
step), test names and fixtures (including the fixture string in
`scripts/tests/test_sdd.py`), comments, and the generated contract
(`contracts/shield-api.openapi.json`, `apps/web/app/types/api.gen.ts`, via
`mise run contract`).

CHANGELOG line under `## [Unreleased]` → `### Removed`:
"SQLite storage and the local password path: Supabase (local stack in
development, Supabase Cloud in production) is the only store and identity
provider (spec 0046)."

## Dead code and criteria

### Code paths that become dead

Local register (`409` for a taken email from `PlayerAlreadyExistsError`), local
login (`InvalidCredentialsError` → `401`), local `_reauthenticate`
(`players.verify_password`), local password change (`players.set_password`),
local email change (immediate move without identity), recovery without Supabase
(silent no-op), the SQLite stores and schema attachment, and the
"Supabase not configured" admin branch (`NoAdminAuthenticator`).

### Tests to remove (dead: only exercise SQLite or the local identity path)

| Test | Criterion | Reason |
| --- | --- | --- |
| `test_clearance.py::test_sqlite_sessions_survive_a_restart_and_expired_rows_are_purged` | API-CLEAR-007 | SQLite session store removed |
| `test_container.py::test_half_configured_supabase_falls_back_to_sqlite` | API-CLEAN-003 | fallback removed (now API-SUPA-001) |
| `test_domain_schemas.py::test_sqlite_stores_use_attached_domain_schemas_that_mirror_the_migrations` | API-SCHEMA-006 | SQLite removed |
| `test_player_confirmation.py::test_local_mode_keeps_immediate_sign_in` | API-VERIFY-007 | local mode removed |
| The SQLite half of `test_game_saves_api.py::test_every_store_saves_and_loads_alike_and_sqlite_survives_restart` | API-SAVE-006 | SQLite restart case removed; in-memory vs Supabase comparison stays |
| The SQLite half of `test_player_confirmation.py::test_password_columns_are_nullable_in_postgres_and_sqlite` | API-VERIFY-009 | replaced by API-SUPA-008 (columns dropped) |
| The local-mode `409`/`401` assertions in `test_game_api.py::test_player_auth_tiers_ai_node_gate_leaderboard_recording_and_daily_quotas` (lines ~401–406) | API-GAME-007 | local identity removed; Supabase-mode equivalents already in API-VERIFY tests |
| The "Supabase not configured" case in `test_clearance.py::test_without_supabase_nobody_can_be_an_admin` | API-CLEAR-015 | Supabase is always configured; other refusal cases stay |

### Tests whose setup changes (behaviour checked is unchanged)

- Harness (`conftest.py`): drop `supabase_players` and `supabase_auth`; always
  wire `SupabasePlayerIdentity` and `SupabaseAdminAuthenticator` over the fake
  auth client, with confirmation off by default (sign-up returns a session).
- Tests that pass `SqliteScoreStore` / `SqlitePlayerStore` / `SqliteSessionStore`
  only as a convenient store switch to the in-memory stores or the fake
  Supabase client: API-ACCOUNT-016/017/018, API-CAMP-002/004, API-CLEAR-016,
  API-CLEAN-003 (`test_without_provider_keys…`, `test_health_reports…`),
  API-CLEAN-004, API-SCHEMA-005, API-AGENT-001/002/003, API-GAME-004,
  API-GAME-007, API-LEVEL-002/003/004, API-VERIFY-014, API-SCORE-004 (or its
  0044 replacement).
- API-ACCOUNT-014 and API-ACCOUNT-019 tests that toggle local vs Supabase mode
  keep only the Supabase mode.
- `scripts/tests/test_sdd.py` references to SQLite paths (if any are about
  `apps/api/var`) are updated.

## Documentation tasks (no cycle needed; listed for the implementer)

- `AGENTS.md`:
  - Commands: delete `mise run local:db:reset # delete the local SQLite databases`;
    change `mise run db:start       # local Supabase (optional; SQLite is the default store)`
    to `mise run db:start       # local Supabase (mise run dev and up start it for you)`;
    change `mise run dev` to `mise run dev            # local Supabase + Redis, then API :8000 + web :3000`;
    add `mise run db:reset        # recreate the local Supabase database`.
  - Architecture rules: change "Add them with `mise run db:migration <name>` and
    never edit a pushed migration. Mirror column changes in `SqliteAuditLog`
    (API-STORE-006 enforces it)." to "Add them with `mise run db:migration <name>`
    and never edit a pushed migration."
- `apps/api/AGENTS.md`: `services/scores.py` row → "`ScoreStore` protocol
  (leaderboard): Supabase, in-memory test double"; `services/players.py` row →
  drop "accounts" password handling wording if present.
- `README.md`: replace the "Storage: … SQLite …" line with "Storage: Supabase
  (local stack in development, Supabase Cloud in production)", and replace the
  Quick start with a **Run it locally** section:
  - Prerequisites: Docker (running) and mise.
  - Native: `mise install && mise run setup && mise run dev` (starts local
    Supabase and Redis, then API :8000 and web :3000).
  - Containers: `mise install && mise run setup && mise run up`.
  - Stop: `mise run down`, `mise run db:stop`.
- `docs/reference/configuration.md`: remove the `SQLITE_PATH` row; `SUPABASE_URL` /
  `SUPABASE_KEY` rows say "Required in every environment".
- `docs/how-to/persist-game-data.md`: rewrite as "Persist game data (Supabase)";
  remove the SQLite sections and `local:db:reset`.
- `docs/how-to/deploy.md`: remove the SQLite volume, single-replica and
  "pick the storage backend" notes; Compose uses local Supabase via
  `host.docker.internal:54321`.
- `docs/explanation/architecture.md` (lines ~57, ~68), `docs/reference/repository-layout.md`
  (lines ~51, ~72, ~78), `docs/reference/http-api.md` (`storage_backend` row and example),
  `docs/reference/cli-and-tasks.md` (`local:db:reset` row → `db:reset`, `infra:up`, `dev`, `up`),
  `docs/README.md` ("Persist game data" link text).
- `apps/api/README.md` (storage and `services/` lines), `apps/api/Dockerfile` (`SQLITE_PATH` env).
- `.claude/skills/tdd/SKILL.md`: drop "and mirror the columns in `SqliteAuditLog`".
- `apps/api/.env.example`: remove `SQLITE_PATH`; the Supabase comment says it is
  required (local: `mise run db:start` then `mise run db:env`).
- `compose.yaml`: remove the `shield-data` volume and mount; keep `extra_hosts` and the
  always-on `redis` service; pass `SUPABASE_URL` / `SUPABASE_KEY` from the environment;
  the header comment says `mise run up` starts local Supabase first.
- `CHANGELOG.md` under `## [Unreleased]` → `### Removed` (exact line under *Sunset*).

## Contract changes (`mise run contract`)

- `HealthResponse.storage_backend`: enum loses `"sqlite"`.

## Security & privacy considerations

- Removes the gateway's own password storage (PBKDF2 hashes and salts) and
  drops those columns: passwords live only in Supabase Auth.
- One identity path means production behaviour (email confirmation, confirmed
  email change from spec 0042) is what developers run locally.
- Fail closed: no silent fallback to a local store in any environment.

## Evaluation impact

ENG-SUPA-001 changes the text of one benign campaign message (`e4_2`). Per
`packages/engine/AGENTS.md`, the implementer records before/after for that
level in this section: the bundled baseline classifier's verdict and score on
`e4_2`, and the wave score of the level's reference board. The bundled
classifier is not retrained.

- **Before (`e4_2` SQLite phrasing):** `load_baseline().score(e4_2.text)` = `Verdict.MALICIOUS` (`score=0.8839`); reference board (`word_filter`) `total_score=10000`, `won=True`, `follow_up_passed=True`.
- **After (`e4_2` Postgres phrasing):** `load_baseline().score(e4_2.text)` = `Verdict.UNCERTAIN` (`score=0.4406`); reference board (`word_filter`) `total_score=10000`, `won=True`, `follow_up_passed=True`.

## Related spec edits (applied)

Approved and applied 2026-11-24; only criterion text changed (Status and
Verification untouched). Retired criteria are struck through with a note.
Spec 0024 is **reworded, not superseded**: its Supabase domain schemas
(`audit`, `game`, `players`) remain the design.

  - 0024: reworded **API-SCHEMA-005** (missing Supabase → `ConfigurationError`); retired **API-SCHEMA-006**.
  - 0012 (clearance sessions): retire **API-CLEAR-007** (SQLite sessions survive
    restart); reword **API-CLEAR-015** (drop "or Supabase not configured") and
    **API-CLEAR-016** ("in the SQLite files" → "in any store").
  - 0016: reword **API-GAME-004** ("persists a score record in SQLite" → "in the
    score store", and recording is by `/game/run`, spec 0042).
  - 0021: reword **API-LEVEL-004** (drop "in SQLite (added with a default on
    start-up…)").
  - 0023: reword **API-SAVE-006** (drop the SQLite restart case; in-memory and
    Supabase stores behave alike).
  - 0025: reword **API-ACCOUNT-016** (drop SQLite), **API-ACCOUNT-017** (drop "and
    the SQLite mirror"), **API-ACCOUNT-020** (email change is confirmed via
    Supabase's flow, spec 0042).
  - 0026: reword **API-CLEAN-004** (drop SQLite).
  - 0027: retire **API-VERIFY-007** (local mode); reword **API-VERIFY-006** (drop
    "exactly as in local mode"), **API-VERIFY-009** (columns dropped, spec 0046),
    **API-VERIFY-014** (drop "or in any SQLite file").
  - 0039: reword **API-CAMP-002** (drop `SqliteScoreStore`/`SqlitePlayerStore` mirroring).
  - 0009 is already `Superseded by 0026`; nothing to do.

## Open questions

None. Resolved 2026-11-24: Implemented-spec wording edits approved and applied;
Compose `redis` stays always on; `mise run dev` / `mise run up` start local
Supabase and Redis; `password_hash` / `salt` are dropped with no safeguard;
SQLite is fully sunset with the listed exceptions.

## Verification

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-SUPA-001, API-SUPA-002, API-SUPA-003, API-SUPA-004, API-SUPA-005, API-SUPA-006, API-SUPA-007, API-SUPA-008, DEV-SUPA-001, DEV-SUPA-002, DEV-SUPA-003, DEV-SUPA-004, DEV-SUPA-005, DEV-SUPA-006, ENG-SUPA-001
- Red: 22 failing test(s) before implementation (`apps/api/tests/test_supabase_only.py::test_missing_supabase_raises_configuration_error_in_every_env[-None-expected_missing0-development]`, `apps/api/tests/test_supabase_only.py::test_missing_supabase_raises_configuration_error_in_every_env[-None-expected_missing0-production]`, `apps/api/tests/test_supabase_only.py::test_missing_supabase_raises_configuration_error_in_every_env[   -key1-expected_missing1-development]`)
- Green: 25 passing test(s)
- Gate: `mise run check` passed
