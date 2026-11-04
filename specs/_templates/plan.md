# NNNN — <Feature name>: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

The design in a few paragraphs. Which modules change, which are new.

## Interfaces

Public types, function signatures, HTTP routes or events that are added or
changed. Mark breaking changes explicitly.

```python
# signatures only, no bodies
```

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New configuration is documented in `docs/reference/configuration.md`

## Alternatives considered

| Option | Why not |
| --- | --- |

## Risks and rollback

What could go wrong in production and how to back it out.
