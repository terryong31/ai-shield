# CLI and tasks reference

## `shield-engine`

Entry point `shield_engine.cli:main`, installed with the engine package. Inside the
monorepo, run it as `uv run shield-engine …` from the repository root.

```
shield-engine [-h] [--version] {train} ...
```

| Global option | Effect |
| --- | --- |
| `-h`, `--help` | Show help |
| `--version` | Print the engine version (e.g. `0.1.0`) |

### `shield-engine train`

Retrain the baseline classifier.

```
shield-engine train --data DATA [--out OUT] [--seed SEED]
```

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--data PATH` | yes | | Training JSONL (`{"text": …, "label": 0 or 1}` per line; see `shield_engine.dataset.load_jsonl`) |
| `--out DIR` | no | `shield_engine.models.BASELINE_DIR` (the bundled `baseline/` directory) | Where to write `model.joblib`, `vectorizer.joblib`, `metadata.json` |
| `--seed N` | no | `42` | `random_state` for `SGDClassifier` |

Prints the new artifact digests (`metadata["files"]`) as JSON.

## `shield-api-export-openapi`

Entry point `shield_api.openapi:main`, installed with the gateway package.

```
uv run shield-api-export-openapi [PATH]
```

Writes the gateway's OpenAPI document (sorted keys, 2-space indent) to `PATH`,
or to `contracts/shield-api.openapi.json` when omitted. It builds the app from
default settings only (`.env` is ignored), so local configuration never leaks
into the contract. Prints `wrote <path>`.

## mise tasks

Defined in [`mise.toml`](../../mise.toml). Run from anywhere in the repository
with `mise run <task>`; list them with `mise tasks`. Tools pinned by mise:
node 24.20.0, bun 1.4.0, uv 0.12.13, python 3.12, supabase 2.116.0, infisical 0.44.11, lefthook 2.2.2,
gitleaks 8.30.1, actionlint 1.7.12, zizmor 1.33.1, shellcheck 0.11.0, semgrep 1.186.0.

| Task | Runs | Description |
| --- | --- | --- |
| `setup` | `mise install`; `uv sync --all-packages`; `bun install`; `lefthook install` | Install tools, all Python and JavaScript dependencies, and the git hooks |
| `hooks:install` | `lefthook install` | Install the git hooks from `lefthook.yml` |
| `docker:ensure` | `docker info`, or `orbctl start` | Make sure that Docker runs |
| `api:dev` | `infisical run --env=dev --path=/api`, then `scripts/local_env.py`, then `uv run uvicorn shield_api.main:app --reload --port 8000` in `apps/api`, with `APP_ENV=development`; depends on `infra:up` | Run the gateway API with reload on :8000 (Swagger at `/api/v1/docs`) |
| `web:dev` | `infisical run --env=dev --path=/web -- bun run dev` in `apps/web` | Run the Nuxt web client on :3000 |
| `dev` | depends on `api:dev`, `web:dev` | Run API and web together |
| `stop` | `kill`, `docker compose stop`, `supabase stop` | Stop the dev servers, Stripe listener, Redis and local Supabase of this repo (data is kept) |
| `stripe:setup` | `python3 scripts/stripe_setup.py <web URL>` | Ask for the sandbox key, store the Stripe variables in Infisical `dev` and `prod`, and make the production webhook endpoint |
| `stripe:events` | `scripts/stripe_setup.py <web URL> --events` with Infisical `prod /api` | Update the events of the production webhook endpoint |
| `stripe:listen` | `stripe listen` with Infisical `dev /api` | Forward Stripe sandbox events to the local API |
| `test:engine` | `uv run pytest packages/engine --cov=shield_engine --cov-fail-under=90` | Engine unit tests with coverage (fails under 90%) |
| `test:api` | `uv run pytest apps/api --cov=shield_api --cov-fail-under=85` | Gateway tests with coverage (fails under 85%) |
| `test:tooling` | `uv run pytest scripts/tests` | Tests for repo tooling (SDD workflow, spec checker) |
| `test:web` | `bun run test` (Vitest) in `apps/web` | Web unit tests |
| `test:e2e` | `bunx playwright test` in `apps/web` | Browser tests against the local stack or `E2E_BASE_URL` ([how-to](../how-to/run-e2e-tests.md)) |
| `e2e:gate` | `python3 scripts/e2e_gate.py` | Run the browser tests against local Supabase; starts and stops the servers when needed |
| `test` | depends on the three test tasks | All tests |
| `lint:py` | `uv run ruff check .`; `uv run ruff format --check .` | Ruff lint + format check |
| `lint:web` | `bun run lint` in `apps/web` | ESLint |
| `lint:actions` | `actionlint`; `zizmor --offline --min-severity medium .github` | Lint the GitHub Actions workflows and audit them for security problems |
| `lint` | depends on `lint:py`, `lint:web`, `lint:actions` | All linters |
| `secrets:scan` | `gitleaks git --redact --no-banner` | Scan the full git history for secrets. Rules: `.gitleaks.toml`; reviewed false positives: `.gitleaksignore` |
| `sast` | `semgrep scan --error --metrics=off --config p/python --config p/typescript --config p/dockerfile --config p/owasp-top-ten .` | Run Semgrep SAST over Python, TypeScript/Vue, and Dockerfiles. Ignored paths: `.semgrepignore` |
| `typecheck:py` | `uv run mypy` | mypy --strict over engine and API |
| `typecheck:web` | `bun run typecheck` in `apps/web` | vue-tsc via nuxt typecheck |
| `typecheck` | depends on both typecheck tasks | (no description) |
| `format` | `uv run ruff format .`; `uv run ruff check --fix .`; `bun run --cwd apps/web lint:fix` | Auto-format everything |
| `contract` | `uv run shield-api-export-openapi`; `bun run --cwd apps/web contract` | Regenerate the OpenAPI contract and the web client's types from it |
| `contract:check` | the two `contract` commands, then `git diff --exit-code -- contracts apps/web/app/types/api.gen.ts` | Fail if the committed contract or generated types are stale |
| `spec:check` | `uv run python scripts/check_spec_coverage.py` | Every acceptance criterion in accepted specs has a test |
| `spec:new` | `uv run python scripts/new_spec.py <slug>` | Scaffold a new spec folder: `mise run spec:new <slug>` |
| `train` | `uv run shield-engine train --data packages/engine/data/seed/train.jsonl` | Retrain the bundled baseline classifier |
| `check` | depends on `lint`, `typecheck`, `test`, `spec:check`, `contract:check`, `secrets:scan`, `sast` | Everything CI runs. Must pass before pushing |
| `build:web` | `bun run build` in `apps/web` | Production build of the web client |
| `sdd:start` | `python3 scripts/sdd.py start` | Start a cycle: `<spec> [IDs…]` or `--refactor "reason"` |
| `sdd:red` | `python3 scripts/sdd.py red` | Run target tests; advance only if each criterion has a legitimately failing test |
| `sdd:green` | `python3 scripts/sdd.py green` | Run target tests; advance only if all pass |
| `sdd:verify` | `python3 scripts/sdd.py verify` | Run `mise run check`; advance only if it passes |
| `sdd:done` | `python3 scripts/sdd.py done` | Set the spec `Implemented`, append `## Verification`, tick `tasks.md` |
| `sdd:status` | `python3 scripts/sdd.py status` | Show the active cycle and next step |
| `sdd:abort` | `python3 scripts/sdd.py abort` | Discard the active cycle |
| `db:start` | `supabase start`, if it does not run; depends on `docker:ensure` | Start the local Supabase stack (applies migrations + seed on first run) |
| `db:stop` | `supabase stop` | Stop the local stack; data is kept |
| `db:status` | `supabase status` | Local URLs and keys |
| `mailpit` | prints `http://127.0.0.1:54424` and `127.0.0.1:54425` | Show the local Mailpit web UI and SMTP address (provided by local Supabase) |
| `db:env` | `supabase status -o json` → two lines | Print `SUPABASE_URL=` / `SUPABASE_KEY=` (service_role) for `apps/api/.env` |
| `db:reset` | `supabase db reset` | Recreate the local database from migrations, then run `supabase/seed.sql` |
| `db:migration` | `supabase migration new <name>` | Create `supabase/migrations/<timestamp>_<name>.sql` |
| `db:diff` | `supabase db diff --schema audit,game,players` | Generate SQL for changes made in Studio (`-f <name>` writes a migration) |
| `db:up` | `supabase migration up` | Apply pending migrations to the local database; data is kept |
| `db:check` | `supabase db start`; `supabase db lint --local --schema audit,game,players --fail-on error` | CI: apply every migration to a new database |
| `db:lint` | `supabase db lint --schema audit,game,players` | Lint the local schema |
| `db:link` | `supabase link` | Link to a hosted project (`--project-ref <ref>`) |
| `db:remote:status` | `supabase migration list` | Compare local and linked migrations (read-only) |
| `db:remote:plan` | `supabase db push --dry-run` | Show the pending migrations of the linked project |
| `db:remote:push` | `supabase db push` | Apply pending migrations to the linked project; never runs seed |
| `db:push` | `supabase db push` | Alias for `db:remote:push` |
| `redis:start` / `redis:stop` | `docker compose up -d redis --wait` / `docker compose stop redis` | Start or stop the local Redis container |
| `infra:up` | `supabase start`, if it does not run; `docker compose up -d redis --wait`; depends on `docker:ensure` | Start local Supabase and Redis |
| `admin:create` | `scripts/local_env.py`, then `python -m shield_api.admin_cli create <email>` | Create a **local** Supabase user as admin, or promote an existing one (`app_metadata.role = "admin"`); prompts for the password |
| `admin:revoke` | `python -m shield_api.admin_cli revoke <email>` | Remove the admin role from a **local** user; other `app_metadata` is kept |
| `admin:remote:create` / `admin:remote:revoke` | The same commands with Infisical `prod /api` | Add or remove an admin in the hosted project |
| `up` | `docker compose up --build` with Infisical `dev /api` and `scripts/local_env.py --docker` | Build and run Redis, API + web containers |
| `down` | `docker compose down` | Stop containers |

## Git hooks (`lefthook.yml`)

`mise run setup` installs the hooks. To skip the hooks for one command, set
`LEFTHOOK=0`. CI runs the same checks, so a skipped hook does not skip the gate.

| Hook | Job | Runs | Files |
| --- | --- | --- | --- |
| `pre-commit` | `secrets` | `gitleaks git --pre-commit --staged` | Staged diff |
| `pre-commit` | `whitespace` | `git diff --cached --check` | Staged files, except `*.md` |
| `pre-commit` | `ruff` | `ruff check --fix`, then `ruff format`; fixes are staged again | Staged `*.py`, `*.pyi` |
| `pre-commit` | `eslint` | `eslint --fix` in `apps/web`; fixes are staged again | Staged `*.ts`, `*.mts`, `*.js`, `*.mjs`, `*.vue`, except `api.gen.ts` |
| `pre-commit` | `sast` | `semgrep scan --error --metrics=off --quiet` | Staged `*.py`, `*.pyi`, `*.ts`, `*.mts`, `*.js`, `*.mjs`, `*.vue`, Dockerfiles, except `api.gen.ts` |
| `pre-commit` | `workflows` | `mise run lint:actions` | Staged files in `.github/` |
| `commit-msg` | `conventional-commit` | Subject line must be a Conventional Commit (`type(scope): text`). `Merge`, `Revert`, `fixup!`, `squash!` and `amend!` subjects are also accepted | Commit message |
| `pre-push` | `protect-main` | Stops a push to `refs/heads/main` | Pushed refs |
| `pre-push` | `full-gate` | `mise run check`. Runs only if `protect-main` passes | Whole repository |

## GitHub Actions (`.github/`)

| File | Trigger | Jobs |
| --- | --- | --- |
| `workflows/ci.yml` | Pull request, push to `main`, merge queue, manual | `Lint`, `Typecheck`, `Test (Python)`, `Test (web)`, `Specs and contract`, `Build (web)`, `Migrations`, `Workflow security`, `Secret scan`, `SAST (Semgrep)`, `Dependency review` (pull requests only), and `CI OK` |
| `workflows/codeql.yml` | Pull request, push to `main`, weekly (Monday 03:17 UTC), manual | CodeQL `security-extended` queries for `python`, `javascript-typescript` and `actions` |
| `workflows/pr-title.yml` | Pull request opened, edited, reopened or updated | The PR title must be a Conventional Commit |
| `actions/setup/action.yml` | Used by the CI jobs | Installs the mise tools, then `uv sync --all-packages --locked` and `bun install --frozen-lockfile`, with caches keyed on `uv.lock` and `bun.lock` |
| Vercel Git integration (not a workflow) | Push to any branch; push to `main` | Deploys the web client (`ai-shield`) and the gateway (`ai-shield-backend`) to a preview URL for each push, and to production for each push to `main`. Reports each deploy as a commit status |
| `dependabot.yml` | Weekly (monthly for actions) | Grouped updates for uv, bun, Docker base images and actions, with a 7-day cooldown |

Each CI job runs the same mise task as a local run. CI does not build the
Docker images; `mise run up` builds them locally. `CI OK` fails if a job
fails or is cancelled. Set `CI OK` as the only required status check in the
branch protection rule for `main`. Every third-party action is pinned to a
full commit SHA, and every job gets read-only `contents` permission unless it
needs more.

## pytest `--spec-ids`

The repo-root `conftest.py` adds two options used by `sdd`:
`--spec-ids=ID1,ID2` runs only tests marked `@pytest.mark.spec` with those
IDs, and `--spec-report=<file>` writes per-test outcomes (and collection errors
of files mentioning the IDs) as JSON.

## Scripts

| Script | Purpose |
| --- | --- |
| [`scripts/new_spec.py`](../../scripts/new_spec.py) `<slug>` | Creates `specs/NNNN-<slug>/` with `spec.md`, `plan.md`, `tasks.md` from `specs/_templates/`, using the next free number and today's date. The slug must be kebab-case (`[a-z0-9]+(-[a-z0-9]+)*`); otherwise it prints usage and exits 2 |
| [`scripts/sdd.py`](../../scripts/sdd.py) `start\|red\|green\|verify\|done\|status\|abort\|hook` | The enforced SDD cycle (spec 0010). State lives in `.sdd/state.json` (git-ignored). `hook pre-tool\|stop\|session-start` reads a Claude Code hook payload on stdin |
| [`scripts/local_env.py`](../../scripts/local_env.py) `[--docker] -- <command>` | Runs a command with the local Supabase and Redis variables. Values that are already in the environment or in `apps/api/.env` stay. `--docker` changes the Supabase host to `host.docker.internal` |
| [`scripts/e2e_gate.py`](../../scripts/e2e_gate.py) | The local browser-test gate ([how-to](../how-to/run-e2e-tests.md#the-local-gate)) |
| [`scripts/redact_traces.py`](../../scripts/redact_traces.py) `<directory>` | Removes credentials from Playwright traces before CI uploads them |
| [`scripts/stripe_setup.py`](../../scripts/stripe_setup.py) `<web URL> [--events]` | Stripe setup, see `stripe:setup` and `stripe:events`. Keys go to Infisical through standard input and are never printed |
| [`scripts/check_spec_coverage.py`](../../scripts/check_spec_coverage.py) | For every `specs/NNNN-*/spec.md` whose `- **Status:**` is `Accepted` or `Implemented`, finds every criterion defined as `- **AREA-COMP-NNN**` and checks that the ID string appears in some file matching `packages/*/tests/**/*.py`, `apps/*/tests/**/*.py`, `apps/*/test/**/*.ts` or `scripts/tests/**/*.py`. Exits 1 and lists missing IDs, otherwise prints `spec coverage OK: N criteria, all traced to tests` |

## Web package scripts (`apps/web/package.json`)

| Script | Command |
| --- | --- |
| `dev` | `nuxt dev` |
| `build` | `nuxt build` |
| `generate` | `nuxt generate` |
| `preview` | `nuxt preview` |
| `lint` / `lint:fix` | `eslint .` / `eslint . --fix` |
| `typecheck` | `nuxt typecheck` |
| `test` / `test:watch` | `vitest run` / `vitest` |
| `contract` | `openapi-typescript ../../contracts/shield-api.openapi.json -o app/types/api.gen.ts` |
