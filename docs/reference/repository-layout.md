# Repository layout

## Tree

```
ai-shield/
├── mise.toml                    # toolchain pins + every task (mise run …)
├── pyproject.toml               # uv workspace root (virtual): members, ruff, mypy, pytest, coverage
├── uv.lock                      # Python lockfile for the whole workspace
├── package.json                 # bun workspaces: ["apps/web"]
├── bun.lock                     # JavaScript lockfile
├── AGENTS.md, CLAUDE.md         # instructions for AI coding agents (see how-to/work-with-ai-agents.md)
├── .claude/                     # Claude Code settings, subagents, skills
├── .github/                     # CI workflows and issue templates
├── .dockerignore, .editorconfig, .gitignore
│
├── packages/
│   └── engine/                  # shield-engine: the framework-free deflector (Python)
│       ├── pyproject.toml       # deps: scikit-learn, joblib; extra [groq]; script shield-engine
│       ├── README.md
│       ├── MODEL_CARD.md        # baseline classifier: data, metrics, limitations
│       ├── data/seed/
│       │   ├── train.jsonl      # 20 training prompts
│       │   └── eval.jsonl       # 40 held-out evaluation prompts
│       ├── src/shield_engine/
│       │   ├── __init__.py      # public API (__all__)
│       │   ├── types.py         # enums and value dataclasses
│       │   ├── events.py        # screen_stream events
│       │   ├── ports.py         # Protocols: ChatModel, FeedbackStore, Classifier, Moderator, Adjudicator
│       │   ├── config.py        # ShieldConfig
│       │   ├── pipeline.py      # Shield: routing
│       │   ├── policy.py        # ToolSpec, allowed_tools (deterministic gate)
│       │   ├── feedback.py      # InMemoryFeedbackStore, CsvFeedbackStore
│       │   ├── detectors/       # classifier.py (Layer 1), moderation.py (Llama Guard)
│       │   ├── adjudication/    # debate.py (Layer 2), fallback.py
│       │   ├── models/          # hash-verified artifact loading + baseline/ artifacts
│       │   ├── training.py      # train_baseline
│       │   ├── evaluation/      # dataset.py, metrics.py, runner.py
│       │   ├── adapters/groq.py # GroqChatModel (optional extra)
│       │   ├── testing.py       # test doubles for hosts
│       │   └── cli.py           # shield-engine eval | train
│       └── tests/
│
├── apps/
│   ├── api/                     # shield-api: FastAPI demo gateway (Python)
│   │   ├── pyproject.toml       # deps: shield-engine[groq], fastapi, supabase, google-genai, …
│   │   ├── Dockerfile           # build from repo root
│   │   ├── .env.example
│   │   ├── src/shield_api/
│   │   │   ├── main.py          # create_app(): CORS, routers, stream schemas in OpenAPI
│   │   │   ├── container.py     # composition root: builds adapters from Settings
│   │   │   ├── settings.py      # environment configuration
│   │   │   ├── schemas.py       # HTTP models + ChatEvent union (the contract)
│   │   │   ├── dependencies.py  # ContainerDep
│   │   │   ├── openapi.py       # shield-api-export-openapi
│   │   │   ├── routers/         # health, screening (/predict, /screen), chat, feedback, audit
│   │   │   ├── services/        # chat.py (stream flow), access.py (clearance, modes), audit.py
│   │   │   └── demo/            # assistant.py, tools.py (catalogue), gemini.py (adapter)
│   │   └── tests/
│   │
│   └── web/                     # @ai-shield/web: Nuxt 4 + Nuxt UI + Vue Flow client
│       ├── nuxt.config.ts       # runtimeConfig.public.apiBaseUrl
│       ├── Dockerfile           # build from repo root
│       ├── .env.example
│       ├── app/
│       │   ├── pages/           # index.vue (main menu + levels), game.vue (defence board), console/{index,logs,settings}.vue (/_console)
│       │   ├── layouts/         # dashboard.vue (UAuthForm-guarded layout for /_console)
│       │   ├── middleware/      # console-redirect.global.ts (/dashboard -> /)
│       │   ├── components/      # chat/, dashboard/, workflow/ (GameNode.vue, etc.)
│       │   ├── composables/     # useShieldApi, useByodSecrets, usePassphrase, useSecurityMode, useShieldWorkflow
│       │   ├── utils/           # gameBoard.ts, chatStream.ts, trace.ts, audit.ts
│       │   └── types/           # api.gen.ts (generated), api.ts (aliases), workflow.ts
│       └── test/                # Vitest
│
├── contracts/
│   └── shield-api.openapi.json  # generated HTTP contract (committed)
├── supabase/                    # `supabase init` project: config.toml, migrations/, seed.sql
├── compose.yaml                 # Docker Compose: api + web, SQLite volume
├── specs/                       # spec-driven development: README, _templates/, NNNN-slug/spec.md
├── scripts/                     # new_spec.py, check_spec_coverage.py
├── docs/                        # this documentation (Diátaxis)
└── reports/                     # evaluation output (git-ignored)
```

Git-ignored runtime and local paths: `apps/api/var/` (feedback CSV), `reports/`,
`.env*` (except `.env.example`), `*.csv`, `*.pkl`, `company_document/`,
`injection_dataset/`, `.claude/settings.local.json`.

## Workspaces

| Ecosystem | Tool | Root file | Members |
| --- | --- | --- | --- |
| Python | uv workspace | `pyproject.toml` | `packages/engine` (`shield-engine`), `apps/api` (`shield-api`) |
| JavaScript | bun workspaces | `package.json` | `apps/web` (`@ai-shield/web`) |

`apps/api` depends on the engine through `[tool.uv.sources] shield-engine = { workspace = true }`.
See [ADR 0001](../explanation/decisions/0001-monorepo-with-uv-and-bun-workspaces.md).

## Dependency rules

| From | May import | Must not import |
| --- | --- | --- |
| `packages/engine` (`shield_engine`) | standard library, `scikit-learn`, `joblib`; `groq` only inside `adapters/groq.py` (optional extra) | `shield_api`, FastAPI, pydantic, Supabase, Google SDKs, any web framework or database client |
| `apps/api` (`shield_api`) | `shield_engine` public API and its submodules (`events`, `models`, `adapters`, `testing` in tests), FastAPI, Supabase, Google GenAI | the web app |
| `apps/web` | the generated contract types (`app/types/api.gen.ts`) and HTTP calls to the gateway | Supabase or any database client, LLM SDKs, Python code |

Consequences:

- Only `apps/api/src/shield_api/container.py` chooses concrete adapters.
- Credentials stop in `apps/api/src/shield_api/services/access.py`; the engine sees only `Clearance`.
- A gateway schema change must go through `mise run contract`; the web client
  typechecks against the regenerated types ([how-to](../how-to/change-the-http-contract.md)).

These rules are also stated in the plan template's "Boundaries check"
([`specs/_templates/plan.md`](../../specs/_templates/plan.md)).
Background: [ADR 0002](../explanation/decisions/0002-engine-gateway-split.md),
[ADR 0004](../explanation/decisions/0004-frontend-talks-only-to-gateway.md).
