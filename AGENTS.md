# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, etc.) and humans
working in this repository. `CLAUDE.md` files import this file. Package-level
`AGENTS.md` files add rules for their own directory.

## What this is

`ai-shield` is an interactive **prompt-injection defence game**: players wire checks on a
board to protect an LLM agent from injection waves. It has three separately deployable parts:

| Path | What | Stack |
| --- | --- | --- |
| `packages/engine` | The game's check library (`shield_engine`), framework-free | Python 3.12, scikit-learn |
| `apps/api` | Game gateway (`shield_api`): players, runs, saves, scores, admin clearance | FastAPI |
| `apps/web` | Game client and the `/_console` admin page | Nuxt 4, Nuxt UI, Vue Flow |

Supporting: `specs/` (specifications), `docs/` (Diátaxis docs),
`contracts/` (OpenAPI contract), `supabase/` (migrations, seed, local config),
`compose.yaml` (containers), `scripts/` (repo tooling).

## Commands

Everything goes through [mise](https://mise.jdx.dev). Never call `pip`, `npm`
or `yarn`; Python uses **uv**, JavaScript uses **bun**.

```bash
mise run setup          # install everything
mise run dev            # API :8000 + web :3000
mise run test           # all tests       (test:engine | test:api | test:web)
mise run lint           # ruff + eslint
mise run typecheck      # mypy --strict + vue-tsc
mise run spec:check     # every acceptance criterion has a test
mise run contract       # regenerate OpenAPI contract + web types
mise run check          # the full CI gate: run before saying you are done
mise run hooks:install  # lefthook git hooks (setup also does this)
mise run train          # retrain the bundled baseline classifier
mise run admin:create <email>  # make a Supabase user an admin (prompts for the password)
mise run up             # API + web in Docker Compose
mise run db:start       # start the local Supabase stack (required for local dev)
```

Run a single Python test: `uv run pytest packages/engine/tests/test_pipeline.py -k skip`.

## How we work: enforced spec-driven + test-driven (mandatory)

Every behaviour change runs one **SDD cycle**. Each step is a command that
checks real evidence and refuses to advance without it (spec 0010). Claude
Code hooks enforce the steps: production code is locked until RED is proven,
agents cannot accept specs, and you cannot end a turn mid-cycle without being
told the next step.

| # | Step | Command | Passes only if |
| --- | --- | --- | --- |
| 1 | **Spec** | `/new-spec` or `mise run spec:new <slug>` | criteria have IDs; the spec stays `Draft`. **Stop: a human sets `Accepted`.** |
| 2 | **Start** | `mise run sdd:start <NNNN> [IDs…]` | the spec is `Accepted` (or `Implemented`, for a fix) |
| 3 | **Write tests** | edit `tests/` only | tag each test `@pytest.mark.spec("ID")`, or `[ID]` in the Vitest name |
| 4 | **Red** | `mise run sdd:red` | every target ID has a test and at least one fails for a legitimate reason (an assertion, or a missing production symbol) |
| 5 | **Code** | edit production code (now unlocked) | the minimum needed |
| 6 | **Green** | `mise run sdd:green` | every test of every target ID passes |
| 7 | **Verify** | `mise run sdd:verify` | the full gate `mise run check` passes |
| 8 | **Done** | `mise run sdd:done` | writes `Implemented` plus a `## Verification` record into the spec and ticks `tasks.md` |

Also: `mise run sdd:status` (where am I, what next) and `mise run sdd:abort`
(discard the cycle). Editing code after `verify` drops you back to green, so
verify again.

- **Bug fixes** use the same cycle: add a criterion or reuse one, write a test
  that reproduces the bug, and prove it red.
- **Refactors** that change no behaviour: `mise run sdd:start --refactor "<reason>"`.
  This unlocks code without a red step, but `sdd:verify` is still required.
- **Docs, specs and config** need no cycle.
- Never mark a spec `Accepted` or `Implemented` by hand, never edit `.sdd/`,
  and never weaken a test to get green.

## Architecture rules (do not break)

- **The engine is pure.** `packages/engine` must never import `fastapi`,
  `supabase`, `shield_api`, or read environment variables. External services
  enter only through the `Protocol`s in `shield_engine/ports.py`. Provider SDKs
  live in `shield_engine/adapters/` behind optional extras.
- **The gateway is thin.** `apps/api` maps HTTP to engine calls, runs the demo
  assistant and owns persistence. Detection logic belongs in the engine. Wiring
  happens only in `shield_api/container.py`.
- **The web client knows only the contract.** `apps/web` talks to the gateway
  through `useShieldApi()` and types from `app/types/api.gen.ts` (generated;
  never edit it). No database clients or secrets in the browser.
- **Credentials stop at the gateway.** The engine receives a `Clearance` enum,
  never a passphrase or token. Never interpolate secrets into LLM prompts.
- **Untrusted text is data.** Any prompt sent to an LLM inside the engine must
  wrap user content with `wrap_untrusted()`. The one exception is score-only
  classifiers (Llama Prompt Guard, ENG-CHECK-006): they get the raw text,
  because they cannot follow instructions and the tags skew their score.
- **Schema changes are migrations.** Add them with `mise run db:migration <name>`
  and never edit a pushed migration.
- **Contract changes are explicit.** Changing `shield_api/schemas.py` means
  running `mise run contract` and committing both generated files.

## Code style

- Python: ruff (lint + format), mypy `--strict`, type hints everywhere,
  frozen dataclasses for engine value types, `Protocol` over ABCs. Use the
  `logging` module, not `print`. Keep comments rare, explaining *why*. Follow PEP 8, PEP 20, PEP 257, PEP 484, PEP 498, PEP 517, PEP 518, PEP 526, PEP 544, PEP 572, PEP 585, PEP 604, PEP 621, PEP 634, PEP 654, PEP 660, PEP 695, and PEP 701 standards. 
- TypeScript/Vue: `<script setup lang="ts">`, Nuxt auto-imports, Nuxt UI
  components only (see `apps/web/AGENTS.md`), no `any`.
- Tests: behaviour-named (`test_malicious_adjudication_blocks_with_shutdown…`),
  Arrange/Act/Assert, and fakes from `shield_engine.testing` rather than mocks.
  No network in tests.
- No emojis allowed in code
- Docs writing method must be following Simplified Technical English (STE), specifically the ASD-STE100 specification.

## Definition of done

- [ ] The cycle was closed with `mise run sdd:done` (spec `Implemented`, verification recorded)
- [ ] `mise run check` passes locally
- [ ] Reference docs in `docs/reference/` reflect the change
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] Scoring or classifier changes: before/after game scores noted in the spec

## Boundaries for agents

- Ask before: adding a dependency, changing a public engine API, changing the
  HTTP contract, editing an `Accepted` spec's criteria, touching CI, deleting files.
- Never: commit secrets or `.env` files, weaken or delete a test to make it
  pass, edit `api.gen.ts` by hand, load pickles that are not hash-verified,
  push to `main`.
- Keep changes scoped to the task; mention unrelated issues rather than fixing them.

## Where to look

- Why things are the way they are: `docs/explanation/` and `docs/explanation/decisions/` (ADRs)
- Exact APIs and config: `docs/reference/`
- Specs and their status: `specs/README.md`
- Model limitations: `packages/engine/MODEL_CARD.md`
