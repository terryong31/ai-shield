# Repository layout

## Tree

```
ai-shield/
├── mise.toml                    # toolchain pins + every task (mise run …)
├── pyproject.toml               # uv workspace root (virtual): members, ruff, mypy, pytest, coverage
├── uv.lock                      # Python lockfile for the whole workspace
├── package.json                 # bun workspaces: ["apps/web"]
├── bun.lock                     # JavaScript lockfile
├── LICENSE                      # MIT
├── AGENTS.md, CLAUDE.md         # instructions for AI coding agents (see how-to/work-with-ai-agents.md)
├── .claude/                     # Claude Code settings, subagents, skills
├── .github/                     # CI workflows, setup action, templates, dependabot
├── lefthook.yml                 # git hooks: pre-commit, commit-msg, pre-push
├── .infisical.json              # Infisical project id and default environment (no secrets)
├── .semgrepignore               # paths that semgrep skips
├── .gitleaks.toml, .gitleaksignore  # secret scan rules and reviewed false positives
├── .dockerignore, .editorconfig, .gitignore
│
├── packages/
│   └── engine/                  # shield-engine: the game's check library (Python)
│       ├── pyproject.toml       # deps: scikit-learn, joblib; extra [groq]; script shield-engine
│       ├── README.md
│       ├── MODEL_CARD.md        # bundled baseline classifier: data, limitations
│       ├── data/seed/train.jsonl # 20 training prompts for the baseline
│       ├── src/shield_engine/
│       │   ├── __init__.py      # public API (__all__)
│       │   ├── types.py         # Verdict, Signal
│       │   ├── ports.py         # Protocols: ChatModel, UsageChatModel, Classifier
│       │   ├── untrusted.py     # wrap_untrusted
│       │   ├── detectors/       # classifier.py (baseline TF-IDF + SGD)
│       │   ├── game/            # board interpreter, checks, levels, agent.py, custom.py, scoring
│       │   ├── models/          # hash-verified artifact loading + baseline/ artifacts
│       │   ├── training.py      # train_baseline
│       │   ├── dataset.py       # load_jsonl, Example
│       │   ├── adapters/groq.py # GroqChatModel (optional extra)
│       │   ├── testing.py       # test doubles for hosts
│       │   └── cli.py           # shield-engine train
│       └── tests/
│
├── apps/
│   ├── api/                     # shield-api: FastAPI game gateway (Python)
│   │   ├── pyproject.toml       # deps: shield-engine[groq], fastapi, supabase, google-genai, httpx, …
│   │   ├── Dockerfile           # build from repo root
│   │   ├── .env.example
│   │   ├── src/shield_api/
│   │   │   ├── main.py          # create_app(): CORS, routers, docs only in development
│   │   │   ├── container.py     # composition root: builds adapters from Settings
│   │   │   ├── settings.py      # environment configuration
│   │   │   ├── schemas.py       # HTTP models (the contract)
│   │   │   ├── dependencies.py  # ContainerDep, client address, rate-limit helper
│   │   │   ├── openapi.py       # shield-api-export-openapi
│   │   │   ├── routers/         # health, auth, account, billing, game, clearance
│   │   │   ├── services/        # players, scores, leaderboard, identity, auth_flows, rate_limit, billing, passes, models, …
│   │   │   └── providers/       # gemini.py (standard-tier agent), byok.py (custom sandbox), typesafe.py (Jev)
│   │   └── tests/
│   │
│   └── web/                     # @ai-shield/web: Nuxt 4 + Nuxt UI + Vue Flow client
│       ├── nuxt.config.ts       # app.head defaults, runtimeConfig.apiProxyTarget, runtimeConfig.public.siteUrl
│       ├── Dockerfile           # build from repo root
│       ├── .env.example
│       ├── public/              # twitter-card.png, twitter-card.svg, favicon.svg, robots.txt, sitemap.xml, llms.txt
│       ├── app/
│       │   ├── pages/           # index.vue (menu + levels), game.vue (board), plans.vue, settings.vue, auth/*, console/{index,settings}.vue (/_console)
│       │   ├── layouts/         # dashboard.vue (UAuthForm-guarded layout for /_console)
│       │   ├── components/      # workflow/GameNode.vue, campaign/*, PasswordStrengthField.vue
│       │   ├── composables/     # useShieldApi, usePlayerAuth, useLeaderboard, useAdminAccess, …
│       │   ├── utils/           # gameBoard.ts, campaignSelect.ts, billing.ts, sessionHint.ts, seo.ts, …
│       │   └── types/           # api.gen.ts (generated), api.ts (aliases)
│       └── test/                # Vitest
│
├── contracts/
│   └── shield-api.openapi.json  # generated HTTP contract (committed)
├── supabase/                    # `supabase init` project: config.toml, migrations/, templates/, seed.sql
├── compose.yaml                 # Docker Compose: redis, api, web
├── specs/                       # spec-driven development: README, _templates/, NNNN-slug/spec.md
├── scripts/                     # sdd.py, new_spec.py, check_spec_coverage.py, local_env.py, redact_traces.py, stripe_setup.py
└── docs/                        # this documentation (Diátaxis)
```

Git-ignored runtime and local paths:
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
- Credentials stop in `apps/api/src/shield_api/services/clearance.py`; the engine sees only `Clearance`.
- A gateway schema change must go through `mise run contract`; the web client
  typechecks against the regenerated types ([how-to](../how-to/change-the-http-contract.md)).

These rules are also stated in the plan template's "Boundaries check"
([`specs/_templates/plan.md`](../../specs/_templates/plan.md)).
Background: [ADR 0002](../explanation/decisions/0002-engine-gateway-split.md),
[ADR 0004](../explanation/decisions/0004-frontend-talks-only-to-gateway.md).
