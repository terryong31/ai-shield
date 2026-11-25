# Architecture decision records

Significant decisions about the structure of `ai-shield`, recorded in the
format described by Michael Nygard: **Context** (the forces at play),
**Decision** (what we chose), **Consequences** (what follows, good and bad).

ADRs are immutable once accepted. To change a decision, write a new ADR that
supersedes the old one and update the old one's status to
`Superseded by NNNN`.

| # | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-monorepo-with-uv-and-bun-workspaces.md) | Monorepo with uv and bun workspaces | Accepted | 2026-09-23 |
| [0002](0002-engine-gateway-split.md) | Split the engine from the gateway | Accepted | 2026-09-23 |
| [0003](0003-spec-driven-and-test-driven-development.md) | Spec-driven and test-driven development | Accepted | 2026-09-23 |
| [0004](0004-frontend-talks-only-to-gateway.md) | The frontend talks only to the gateway | Accepted | 2026-09-23 |
| [0005](0005-ndjson-event-stream.md) | NDJSON event stream for `/chat` | Superseded by spec 0026 | 2026-09-23 |
| [0006](0006-hash-verified-model-artifacts.md) | Hash-verified model artifacts | Accepted | 2026-09-23 |
| [0007](0007-ci-pipeline-and-git-hooks.md) | CI pipeline and git hooks | Accepted | 2026-11-24 |
| [0008](0008-infisical-for-secrets.md) | Infisical for secrets | Proposed | 2026-11-25 |
| [0009](0009-one-time-pass-with-stripe.md) | One-time pass with Stripe Checkout | Accepted | 2026-11-25 |

## Template

```markdown
# NNNN. Title

- **Status:** Proposed | Accepted | Superseded by NNNN
- **Date:** YYYY-MM-DD

## Context

## Decision

## Consequences
```
