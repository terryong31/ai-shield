# Change the HTTP contract

The gateway's request and response models in
[`apps/api/src/shield_api/schemas.py`](../../apps/api/src/shield_api/schemas.py)
are the public contract. They are exported to
[`contracts/shield-api.openapi.json`](../../contracts/shield-api.openapi.json),
from which the web client's types (`apps/web/app/types/api.gen.ts`) are
generated. This guide uses an example: adding a `wave_size` field to
`GameLevelSchema` so the level cards can show how many prompts a wave has.

## 1. Spec it

A contract change is a behaviour change. Add criteria to the owning spec
(for example [0016](../../specs/0016-game-engine/spec.md) for the game routes) or create a new spec. Get
approval first: [`AGENTS.md`](../../AGENTS.md) lists HTTP contract changes as
"ask before". Say whether the change is breaking:

| Change | Breaking for existing clients |
| --- | --- |
| Add an optional response field | no |
| Add a required request field, remove or rename any field, narrow a type | yes |

## 2. Write the failing test

In `apps/api/tests/`, for example:

```python
@pytest.mark.spec("API-GAME-010")
def test_levels_report_their_wave_size(harness) -> None:
    levels = harness.client.get("/api/v1/game/levels").json()["levels"]

    assert all(level["wave_size"] == len(level["messages"]) for level in levels)
```

## 3. Edit the schema and the route

```python
class GameLevelSchema(BaseModel):
    ...
    wave_size: int = 0
```

And populate it in [`routers/game.py`](../../apps/api/src/shield_api/routers/game.py)
where the level catalog is built.

Run the gateway tests. The new test passes, and the drift test fails:

```bash
mise run test:api
```

```
FAILED apps/api/tests/test_contract.py::test_committed_contract_is_up_to_date - AssertionError: Contract drifted: run `mise run contract` and commit the result
```

That is `API-CONTRACT-001`: the committed contract must equal what the app generates.

## 4. Regenerate the contract and client types

```bash
mise run contract
```

This runs `uv run shield-api-export-openapi` (writes the contract from default
settings) and `bun run --cwd apps/web contract` (runs `openapi-typescript` to
rewrite `app/types/api.gen.ts`). Never edit `api.gen.ts` by hand.

Review the diff of both files. It should contain only what you intended.

## 5. Update the web client

- If you want a friendly name, add an alias in
  [`apps/web/app/types/api.ts`](../../apps/web/app/types/api.ts).
- New calls go in [`useShieldApi.ts`](../../apps/web/app/composables/useShieldApi.ts),
  the only module that talks to the gateway.
- Logic worth testing goes in `app/utils/` as pure functions, with a Vitest
  test named `[WEB-…] …`.

Then type-check. A breaking change surfaces here:

```bash
mise run typecheck:web
mise run test:web
```

## 6. Check and commit

```bash
mise run contract:check
mise run check
```

`contract:check` regenerates both files, then runs
`git diff --exit-code -- contracts apps/web/app/types/api.gen.ts`. `git diff`
compares the working tree with the git index, so locally it fails until you
stage the regenerated files:

```bash
git add contracts/shield-api.openapi.json apps/web/app/types/api.gen.ts
```

In CI (the "Specs & contract" job) it fails whenever the committed files are stale.

Commit together: `schemas.py`, the route or service change, `contracts/shield-api.openapi.json`,
`apps/web/app/types/api.gen.ts`, client changes, tests, and an update to the
[HTTP API reference](../reference/http-api.md).

## Background

- [ADR 0004: The frontend talks only to the gateway](../explanation/decisions/0004-frontend-talks-only-to-gateway.md)
