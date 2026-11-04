# 0005 — Tool policy gate

- **Status:** Implemented
- **Area:** ENG
- **Created:** 2026-09-23
- **Related:** spec 0001

## Problem

A decision is only useful if the host can turn it into concrete permissions.
The policy-to-tools mapping was inlined in the chat route and one demo tool
(`drop_database_table`) was mislabelled `LOW` risk, so it stayed available
under `RESTRICTED`.

## Behaviour

`allowed_tools(policy, tools)` filters a catalogue of `ToolSpec(name, risk)`:

| Policy | Allowed |
| --- | --- |
| `ALLOW_ALL` | every tool |
| `RESTRICTED` | tools with risk `LOW` only |
| `SHUTDOWN` | none |

Order of the input catalogue is preserved.

## Acceptance criteria

- **ENG-POL-001**: Given `ALLOW_ALL`, then all tools are allowed, in catalogue order.
- **ENG-POL-002**: Given `RESTRICTED`, then only `LOW`-risk tools are allowed.
- **ENG-POL-003**: Given `SHUTDOWN`, then no tools are allowed.

## Security & privacy considerations

The gate is deterministic code, deliberately outside any LLM, so a successful
injection against Layer 2 still cannot unlock tools beyond the policy it
emits. Correct risk labels are part of the security boundary; the demo
catalogue's labels are covered by API tests.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: ENG-POL-001, ENG-POL-002, ENG-POL-003
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 3 passing test(s)
- Gate: `mise run check` passed
