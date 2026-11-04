# ai-shield documentation

`ai-shield` is a layered prompt-injection deflector and interactive workflow defence game for LLM applications.
The engine (`packages/engine`) decides whether a prompt may reach an
application and with which tools, and powers the node-based defence board; the gateway (`apps/api`) and web client
(`apps/web`) expose the game (`/`, `/game`) and the login-guarded security console (`/_console`).

These docs follow the [Diátaxis](https://diataxis.fr) framework. Pick the
quadrant that matches what you need right now:

| | **Practical steps** | **Theoretical knowledge** |
| --- | --- | --- |
| **While learning** | [Tutorials](#tutorials): lessons that take you through a task | [Explanation](#explanation): background, design and reasoning |
| **While working** | [How-to guides](#how-to-guides): recipes for specific goals | [Reference](#reference): exact, complete technical description |

## Tutorials

Start here if you are new.

1. [Run the demo](tutorials/01-run-the-demo.md): install, start everything, see a prompt allowed and one blocked.
2. [Embed the engine](tutorials/02-embed-the-engine.md): screen prompts from your own Python script, stream events, map policies to tools, simulate Layer 2.
3. [Your first spec-driven change](tutorials/03-your-first-spec-driven-change.md): spec, failing test, code, gate, end to end.

## How-to guides

- [Configure LLM providers](how-to/configure-llm-providers.md): enable Groq and Gemini, choose models, know what degrades without them.
- [Persist the audit log](how-to/persist-the-audit-log.md): SQLite by default; run, migrate and deploy the Supabase project in `supabase/`.
- [Retrain the classifier](how-to/retrain-the-classifier.md): edit training data, retrain, verify digests, update the model card.
- [Run evaluations](how-to/run-evaluations.md): benchmark the classifier or full pipeline, on the seed set or your own data.
- [Add a detector](how-to/add-a-detector.md): implement a new classifier or moderator behind the ports and wire it in.
- [Change the HTTP contract](how-to/change-the-http-contract.md): edit schemas, regenerate the contract and client types.
- [Write a spec](how-to/write-a-spec.md): checklist for IDs, status, traceability and review.
- [Deploy](how-to/deploy.md): build the Docker images, configure them, and harden for production.
- [Work with AI agents](how-to/work-with-ai-agents.md): use AGENTS.md, Claude Code permissions, subagents and skills.

## Reference

- [Engine API](reference/engine-api.md): every public class, function and field of `shield_engine`.
- [HTTP API](reference/http-api.md): gateway routes, request and response fields, status codes, the NDJSON event protocol.
- [Configuration](reference/configuration.md): environment variables for the gateway and web client, engine constructor options.
- [CLI and tasks](reference/cli-and-tasks.md): `shield-engine`, `shield-api-export-openapi`, every `mise` task and script.
- [Verdicts and policies](reference/verdicts-and-policies.md): enums, the routing table, the fallback and the tool policy gate.
- [Repository layout](reference/repository-layout.md): annotated tree and dependency rules.

## Explanation

- [Architecture](explanation/architecture.md): the three deployables, ports and adapters, the composition root, the `/chat` lifecycle.
- [Defense in depth](explanation/defense-in-depth.md): why the layers are ordered as they are, failure modes, why the policy gate is plain code.
- [Threat model](explanation/threat-model.md): assets, actors, trust boundaries, threats, mitigations and known gaps.
- [Evaluation methodology](explanation/evaluation-methodology.md): metric choices, abstention, dataset hygiene, small-sample caveats.
- [Development process](explanation/development-process.md): why spec-driven plus test-driven, traceability, CI, AI agents.
- [Architecture decision records](explanation/decisions/README.md): the recorded decisions and their consequences.

## Elsewhere in the repository

- [Specifications](../specs/README.md): the spec process and the index of all specs.
- [ADR index](explanation/decisions/README.md)
- [Model card](../packages/engine/MODEL_CARD.md): the baseline classifier's data, metrics and limitations.
- [HTTP contract](../contracts/shield-api.openapi.json): the committed OpenAPI document.
