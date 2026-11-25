# ai-shield documentation

`ai-shield` is an interactive prompt-injection defence game. Players wire checks
on a node board to protect an LLM agent from injection waves. The engine
(`packages/engine`) evaluates boards, runs the AI agent and scores waves; the
gateway (`apps/api`) owns players, quotas, saves and the leaderboard; the web
client (`apps/web`) renders the game (`/`, `/game`, `/plans`, `/settings`) and
the admin console (`/_console`).

These docs follow the [Diátaxis](https://diataxis.fr) framework. Pick the
quadrant that matches what you need right now:

| | **Practical steps** | **Theoretical knowledge** |
| --- | --- | --- |
| **While learning** | [Tutorials](#tutorials): lessons that take you through a task | [Explanation](#explanation): background, design and reasoning |
| **While working** | [How-to guides](#how-to-guides): recipes for specific goals | [Reference](#reference): exact, complete technical description |

## Tutorials

1. [Run the game](tutorials/01-run-the-demo.md): install, start everything, play a level.
2. [Your first spec-driven change](tutorials/03-your-first-spec-driven-change.md): spec, failing test, code, gate, end to end.

## How-to guides

- [Manage secrets](how-to/manage-secrets.md): set up Infisical, add a secret, work without access.
- [Accept payments](how-to/accept-payments.md): set up Stripe, test a payment, find a problem, go live.
- [Configure LLM providers](how-to/configure-llm-providers.md): enable Groq and Gemini for the game's AI agent tiers.
- [Persist game data](how-to/persist-game-data.md): run, migrate and deploy the Supabase project in `supabase/`.
- [Retrain the classifier](how-to/retrain-the-classifier.md): retrain the bundled baseline (no check uses it at this time), verify digests, update the model card.
- [Change the HTTP contract](how-to/change-the-http-contract.md): edit schemas, regenerate the contract and client types.
- [Write a spec](how-to/write-a-spec.md): checklist for IDs, status, traceability and review.
- [Deploy](how-to/deploy.md): build the Docker images, configure them, and harden for production.
- [Work with AI agents](how-to/work-with-ai-agents.md): use AGENTS.md, Claude Code permissions, subagents and skills.
- [Work with CI and the git hooks](how-to/work-with-ci-and-git-hooks.md): install the hooks, fix a failed hook or CI job, change the pipeline.

## Reference

- [Engine API](reference/engine-api.md): every public class, function and field of `shield_engine`.
- [HTTP API](reference/http-api.md): gateway routes, request and response fields, status codes.
- [Configuration](reference/configuration.md): environment variables for the gateway and web client, engine options.
- [CLI and tasks](reference/cli-and-tasks.md): `shield-engine train`, `shield-api-export-openapi`, every `mise` task and script, the git hooks and the GitHub Actions workflows.
- [Repository layout](reference/repository-layout.md): annotated tree and dependency rules.

## Explanation

- [Architecture](explanation/architecture.md): the three deployables, ports and adapters, the composition root, the life of a wave run.
- [Threat model](explanation/threat-model.md): assets, actors, trust boundaries, threats, mitigations and known gaps.
- [Development process](explanation/development-process.md): why spec-driven plus test-driven, traceability, CI and git hooks, AI agents.
- [Architecture decision records](explanation/decisions/README.md): the recorded decisions and their consequences.

## Elsewhere in the repository

- [Specifications](../specs/README.md): the spec process and the index of all specs.
- [Model card](../packages/engine/MODEL_CARD.md): the bundled baseline classifier.
- [HTTP contract](../contracts/shield-api.openapi.json): the committed OpenAPI document.
