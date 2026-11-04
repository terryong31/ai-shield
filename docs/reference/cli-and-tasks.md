# CLI and tasks reference

## `shield-engine`

Entry point `shield_engine.cli:main`, installed with the engine package. Inside the
monorepo, run it as `uv run shield-engine …` from the repository root.

```
shield-engine [-h] [--version] {eval,train} ...
```

| Global option | Effect |
| --- | --- |
| `-h`, `--help` | Show help |
| `--version` | Print the engine version (e.g. `0.1.0`) |

### `shield-engine eval`

Evaluate the pipeline on a labelled JSONL dataset.

```
shield-engine eval --data DATA [--report REPORT] [--pipeline {classifier,full}]
```

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--data PATH` | yes | | JSONL dataset ([format](../how-to/run-evaluations.md#dataset-format)) |
| `--report PATH` | no | none | Write the JSON report here (parent directories are created) |
| `--pipeline` | no | `classifier` | `classifier`: bundled baseline only. `full`: baseline + `LlamaGuardModerator` + `DebateAdjudicator` over Groq |

`--pipeline full` reads `GROQ_API_KEY` (required; the command exits with
`--pipeline full needs GROQ_API_KEY in the environment` otherwise),
`GROQ_GUARD_MODEL` (default `llama-guard-3-8b`) and `GROQ_DEBATE_MODEL`
(default `llama-3.3-70b-versatile`). Evaluation uses clearance `NONE` and the
default `ShieldConfig`.

Standard output, one line:

```
n=40  precision=1.000  recall=0.550  f1=0.710  fpr=0.000  abstain=0.375  p50=0.13ms
```

Report JSON:

| Key | Type | Meaning |
| --- | --- | --- |
| `engine_version` | string | `shield_engine.__version__` |
| `pipeline` | string | `classifier` or `full` |
| `dataset.path` | string | `--data` as given |
| `dataset.sha256` | string | SHA-256 of the dataset file |
| `examples` | integer | Number of rows |
| `metrics.tp`, `fp`, `tn`, `fn` | integer | Confusion matrix (positive = blocked) |
| `metrics.precision`, `recall`, `f1`, `false_positive_rate`, `accuracy` | number | 0.0 on zero denominators |
| `abstention_rate` | number | Share of `UNCERTAIN` final verdicts |
| `latency_ms.p50`, `latency_ms.p95` | number | Per-prompt screening latency |

Exit code 0 on success. Dataset errors raise `DatasetError` (non-zero exit with a traceback).

### `shield-engine train`

Retrain the baseline classifier.

```
shield-engine train --data DATA [--out OUT] [--seed SEED]
```

| Option | Required | Default | Meaning |
| --- | --- | --- | --- |
| `--data PATH` | yes | | Training JSONL |
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
node 24.20.0, bun 1.4.0, uv 0.12.13, python 3.12, supabase 2.116.0.

| Task | Runs | Description |
| --- | --- | --- |
| `setup` | `uv sync --all-packages`; `bun install` | Install all Python and JavaScript dependencies |
| `api:dev` | `uv run uvicorn shield_api.main:app --reload --port 8000` in `apps/api` | Run the gateway API with reload on :8000 |
| `web:dev` | `bun run dev` in `apps/web` | Run the Nuxt web client on :3000 |
| `dev` | depends on `api:dev`, `web:dev` | Run API and web together |
| `test:engine` | `uv run pytest packages/engine --cov=shield_engine --cov-fail-under=90` | Engine unit tests with coverage (fails under 90%) |
| `test:api` | `uv run pytest apps/api --cov=shield_api --cov-fail-under=85` | Gateway tests with coverage (fails under 85%) |
| `test:tooling` | `uv run pytest scripts/tests` | Tests for repo tooling (SDD workflow, spec checker) |
| `test:web` | `bun run test` (Vitest) in `apps/web` | Web unit tests |
| `test` | depends on the three test tasks | All tests |
| `lint:py` | `uv run ruff check .`; `uv run ruff format --check .` | Ruff lint + format check |
| `lint:web` | `bun run lint` in `apps/web` | ESLint |
| `lint` | depends on `lint:py`, `lint:web` | (no description) |
| `typecheck:py` | `uv run mypy` | mypy --strict over engine and API |
| `typecheck:web` | `bun run typecheck` in `apps/web` | vue-tsc via nuxt typecheck |
| `typecheck` | depends on both typecheck tasks | (no description) |
| `format` | `uv run ruff format .`; `uv run ruff check --fix .`; `bun run --cwd apps/web lint:fix` | Auto-format everything |
| `contract` | `uv run shield-api-export-openapi`; `bun run --cwd apps/web contract` | Regenerate the OpenAPI contract and the web client's types from it |
| `contract:check` | the two `contract` commands, then `git diff --exit-code -- contracts apps/web/app/types/api.gen.ts` | Fail if the committed contract or generated types are stale |
| `spec:check` | `uv run python scripts/check_spec_coverage.py` | Every acceptance criterion in accepted specs has a test |
| `spec:new` | `uv run python scripts/new_spec.py <slug>` | Scaffold a new spec folder: `mise run spec:new <slug>` |
| `eval` | `uv run shield-engine eval --data packages/engine/data/seed/eval.jsonl --report reports/eval-classifier.json` | Evaluate the baseline pipeline on the held-out seed set |
| `train` | `uv run shield-engine train --data packages/engine/data/seed/train.jsonl` | Retrain the bundled baseline classifier |
| `check` | depends on `lint`, `typecheck`, `test`, `spec:check`, `contract:check` | Everything CI runs. Must pass before pushing |
| `build:web` | `bun run build` in `apps/web` | Production build of the web client |
| `sdd:start` | `python3 scripts/sdd.py start` | Start a cycle: `<spec> [IDs…]` or `--refactor "reason"` |
| `sdd:red` | `python3 scripts/sdd.py red` | Run target tests; advance only if each criterion has a legitimately failing test |
| `sdd:green` | `python3 scripts/sdd.py green` | Run target tests; advance only if all pass |
| `sdd:verify` | `python3 scripts/sdd.py verify` | Run `mise run check`; advance only if it passes |
| `sdd:done` | `python3 scripts/sdd.py done` | Set the spec `Implemented`, append `## Verification`, tick `tasks.md` |
| `sdd:status` | `python3 scripts/sdd.py status` | Show the active cycle and next step |
| `sdd:abort` | `python3 scripts/sdd.py abort` | Discard the active cycle |
| `db:start` | `supabase start` | Start the local Supabase stack (applies migrations + seed on first run) |
| `db:stop` | `supabase stop` | Stop the local stack; data is kept |
| `db:status` | `supabase status` | Local URLs and keys |
| `db:env` | `supabase status -o json` → two lines | Print `SUPABASE_URL=` / `SUPABASE_KEY=` (service_role) for `apps/api/.env` |
| `db:reset` | `supabase db reset` | Recreate the local database from migrations, then run `supabase/seed.sql` |
| `db:migration` | `supabase migration new <name>` | Create `supabase/migrations/<timestamp>_<name>.sql` |
| `db:diff` | `supabase db diff --schema public` | Generate SQL for changes made in Studio (`-f <name>` writes a migration) |
| `db:lint` | `supabase db lint --schema public` | Lint the local schema |
| `db:link` | `supabase link` | Link to a hosted project (`--project-ref <ref>`) |
| `db:push` | `supabase db push` | Apply pending migrations to the linked project; never runs seed |
| `up` | `docker compose up --build` | Build and run API + web containers |
| `down` | `docker compose down` | Stop containers; the `shield-data` volume is kept |

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
| [`scripts/check_spec_coverage.py`](../../scripts/check_spec_coverage.py) | For every `specs/NNNN-*/spec.md` whose `- **Status:**` is `Accepted` or `Implemented`, finds every criterion defined as `- **AREA-COMP-NNN**` and checks that the ID string appears in some file matching `packages/*/tests/**/*.py`, `apps/*/tests/**/*.py` or `apps/*/test/**/*.ts`. Exits 1 and lists missing IDs, otherwise prints `spec coverage OK: N criteria, all traced to tests` |

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
