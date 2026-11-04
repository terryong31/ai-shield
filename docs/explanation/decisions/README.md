# Architecture decision records

Significant decisions about the structure of AI S.H.I.E.L.D., recorded in the
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
| [0005](0005-ndjson-event-stream.md) | NDJSON event stream for `/chat` | Accepted | 2026-09-23 |
| [0006](0006-hash-verified-model-artifacts.md) | Hash-verified model artifacts | Accepted | 2026-09-23 |

## Template

```markdown
# NNNN. Title

- **Status:** Proposed | Accepted | Superseded by NNNN
- **Date:** YYYY-MM-DD

## Context

## Decision

## Consequences
```
