# ai-shield

**An interactive prompt-injection defence game for LLM applications.**

Players wire checks on a node board to protect an LLM agent from waves of prompt
injections, then score on protection, helpfulness, tool use, tokens, speed and cost.
The game runs on a framework-free Python check library (`shield-engine`), a FastAPI
gateway (`shield-api`) and a Nuxt web client (`@ai-shield/web`).

```
Input ──▶ [Text cleaner / Word filter / Length limit / Secret scanner / ML filter /
           Quick screen / Safety check / LLM review / Tool filter] ──▶ Help Desk or Protected Agent
```

## Repository

| Path | What | Stack |
| --- | --- | --- |
| [`packages/engine`](packages/engine) | **Engine** (`shield-engine`): board interpreter, checks, levels, AI agent, custom sandbox and scoring | Python 3.12, scikit-learn |
| [`apps/api`](apps/api) | **Gateway** (`shield-api`): players and quotas, runs, saved boards, leaderboard, admin clearance | FastAPI, SQLite / Supabase |
| [`apps/web`](apps/web) | **Web client** (`@ai-shield/web`): main menu (`/`), defence board (`/game`), plans (`/plans`), settings and the admin console (`/_console`) | Nuxt 4, Nuxt UI, Vue Flow |

The web client talks only to the gateway through a committed [OpenAPI contract](contracts/shield-api.openapi.json). The gateway holds no detection logic; checks, graph evaluation, custom ML training and wave scoring live in `shield-engine`.

## Quick start

```bash
# prerequisites: mise (https://mise.jdx.dev)
mise install          # pins Python, uv, Node, bun
mise run setup        # installs all dependencies
mise run dev          # API on :8000 (Swagger at /api/v1/docs), web on :3000
```

Open http://localhost:3000:

1. **Main menu (`/`):** pick a level (Easy: classify prompts at a Help Desk; Medium: protect a modern AI agent; Hard: protect a budget model), see the leaderboard, open **Plans** to upgrade, and paid players get the **Custom** sandbox (your own agent, dataset and model key).
2. **Defence board (`/game`):** drag checks from **Tools**, wire them between **Input** and the final node, double-click a node to configure it, then **Run wave**. Signed-in players get 5 attempts a day on Medium and Hard (anonymous 1, paid 300) and can **Save** their board.
3. **Admin console (`/_console`):** for Supabase users with `app_metadata.role = "admin"` (create one with `mise run admin:create <email>`); shows score stats and the leaderboard, and can clear the scoreboard.

- **Containers:** `mise run up` builds and runs both apps with [`compose.yaml`](compose.yaml).
- **Storage:** players, saved boards, scores and admin sessions go to SQLite under `apps/api/var/` by default (`mise run local:db:reset` wipes it). For Supabase see [persist game data](docs/how-to/persist-game-data.md).

## Documentation

Docs follow the [Diátaxis](https://diataxis.fr) framework. Start at **[docs/](docs/README.md)**.

| Learn | Do | Look up | Understand |
| --- | --- | --- | --- |
| [Tutorials](docs/tutorials/) | [How-to guides](docs/how-to/) | [Reference](docs/reference/) | [Explanation](docs/explanation/) |

Also see the [model card](packages/engine/MODEL_CARD.md) for the baseline classifier behind the `Quick screen` check.

## How we build it

Development is **spec-driven and test-driven**:

1. Every behaviour change starts as a spec in [`specs/`](specs/README.md) with acceptance criteria carrying permanent IDs (`ENG-GAME-001`, `WEB-GAME-005`).
2. Each criterion gets a failing test tagged with its ID before production code is unlocked (`mise run sdd:start` -> `sdd:red` -> `sdd:green` -> `sdd:verify` -> `sdd:done`).
3. `mise run check` verifies spec coverage (`mise run spec:check`), contract drift (`mise run contract:check`), strict typechecking (`mypy` + `vue-tsc`), linters (`ruff` + `eslint`), and test suites across engine, API, and web.

See [AGENTS.md](AGENTS.md) and [docs/how-to/work-with-ai-agents.md](docs/how-to/work-with-ai-agents.md).

## Contributing, security, citation

- [CONTRIBUTING.md](CONTRIBUTING.md)
- Found a bypass or vulnerability? Follow [SECURITY.md](SECURITY.md); please do not open a public issue.
- Using this in research? Cite it via [CITATION.cff](CITATION.cff).
- Release history: [CHANGELOG.md](CHANGELOG.md)

## License

No license has been granted yet: all rights reserved by the copyright holder until a `LICENSE` file is added.
