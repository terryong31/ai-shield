# Change the HTTP contract

The gateway's request, response and stream-event models in
[`apps/api/src/shield_api/schemas.py`](../../apps/api/src/shield_api/schemas.py)
are the public contract. They are exported to
[`contracts/shield-api.openapi.json`](../../contracts/shield-api.openapi.json),
from which the web client's types (`apps/web/app/types/api.gen.ts`) are
generated. This guide uses an example: adding moderation categories to
`ScreenResponse`.

## 1. Spec it

A contract change is a behaviour change. Add criteria to the gateway spec
([0007](../../specs/0007-gateway-http-api/spec.md)) or create a new spec. Get
approval first: [`AGENTS.md`](../../AGENTS.md) lists HTTP contract changes as
"ask before". Say whether the change is breaking:

| Change | Breaking for existing clients |
| --- | --- |
| Add an optional response field | no |
| Add a required request field, remove or rename any field, narrow a type | yes |
| Add a new `ChatEvent` type | no for the web client (it ignores unknown types in `applyChatEvent`), but document it |

## 2. Write the failing test

In `apps/api/tests/`, for example:

```python
@pytest.mark.spec("API-SCREEN-002")
def test_screen_reports_moderation_categories(harness) -> None:
    response = harness.client.post("/api/v1/screen", json={"message": "hello"})

    assert response.json()["moderation_categories"] == []
```

## 3. Edit the schema and the route

```python
class ScreenResponse(BaseModel):
    ...
    moderation_categories: list[str] = Field(default_factory=list)
```

And populate it in [`routers/screening.py`](../../apps/api/src/shield_api/routers/screening.py)
from `decision.moderation`. For a new stream event, add the model to the
`ChatEvent` union in `schemas.py` and yield it from
[`services/chat.py`](../../apps/api/src/shield_api/services/chat.py).

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
- New stream events: handle them in `applyChatEvent` in
  [`app/utils/chatStream.ts`](../../apps/web/app/utils/chatStream.ts), with a
  Vitest test named `[WEB-…] …`.

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
- [ADR 0005: NDJSON event stream](../explanation/decisions/0005-ndjson-event-stream.md)
