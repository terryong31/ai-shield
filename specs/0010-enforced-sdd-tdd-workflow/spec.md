# 0010 — Enforced SDD + TDD workflow for AI agents

- **Status:** Accepted
- **Area:** DEV
- **Created:** 2026-09-23
- **Related:** [development process](../../docs/explanation/development-process.md), [work with AI agents](../../docs/how-to/work-with-ai-agents.md), `AGENTS.md`

## Problem

The spec-first, test-first process was only written down. Nothing stopped an
agent from editing production code before a failing test existed, from calling
a test "red" without running it, from accepting its own spec, or from
declaring work done without running the full gate. Instructions alone are
advisory; the process needs mechanical enforcement.

## Goals

- One explicit, auditable lifecycle per change:
  **spec → red → green → verified → done**.
- Each transition is a command that checks real evidence (test runs, gate runs)
  before advancing.
- Claude Code hooks make the lifecycle binding for agents.
- Completing a cycle updates the spec with a verification record.

## Non-goals

- Policing humans. The guard runs as an agent hook, and CI only checks
  outcomes (coverage, verification records).
- Perfect detection of shell-based file writes. The Bash guard is a best-effort heuristic.

## Behaviour

State lives in `.sdd/state.json` (git-ignored, one active cycle per checkout).

| Command (`mise run …`) | Precondition | Evidence checked | New phase |
| --- | --- | --- | --- |
| `sdd:start <NNNN> [IDs…]` | spec status `Accepted` or `Implemented`; IDs exist in the spec | none | `spec` |
| `sdd:start --refactor "<reason>"` | none | none | `refactor` |
| `sdd:red` | phase `spec` | every target ID has ≥1 test, and ≥1 of them fails for a legitimate reason | `red` |
| `sdd:green` | phase `red` or `green` | every test of every target ID passes | `green` |
| `sdd:verify` | phase `green` or `refactor` | the full gate (`mise run check`) passes | `verified` |
| `sdd:done` | phase `verified` | none | cycle closed |
| `sdd:status` | none | none | unchanged |
| `sdd:abort` | none | none | cycle discarded |

A **legitimate failure** is an assertion or runtime failure inside a test, or a
test module that cannot import a production symbol (`shield_engine` or
`shield_api`) that does not exist yet. Any other collection or syntax error in
test code is not red.

`sdd:done` sets the spec status to `Implemented`, ticks the matching items in
`tasks.md`, and appends a verification entry to the spec under
`## Verification` (date, commit, IDs, red failures, green passes, gate result).
In refactor mode it touches no spec.

Agent guard (Claude Code `PreToolUse` on Edit/Write):

| File class | Allowed when |
| --- | --- |
| production (`packages/*/src/**`, `apps/api/src/**`, `apps/web/app/**`, `supabase/migrations/**`) | phase is `red`, `green`, `verified` or `refactor` |
| tests (`**/tests/**`, `apps/web/test/**`, `shield_engine/testing.py`) | any active cycle |
| everything else (specs, docs, config) | always, except the rule below |

An agent edit that changes a spec's status to `Accepted` or `Implemented` is
always denied: acceptance is a human decision, and `Implemented` is written
only by `sdd:done`. Editing production or tests while `verified` moves the
cycle back to `green`, so the gate must be re-run.

## Acceptance criteria

- **DEV-SDD-001**: `start` refuses a spec that is missing or has a status other than `Accepted`/`Implemented`, and refuses IDs that the spec does not define; otherwise it records the spec and its target IDs (all criteria by default) in phase `spec`.
- **DEV-SDD-002**: `red` refuses to advance, and names the IDs, when any target ID has no test.
- **DEV-SDD-003**: `red` advances only if every target ID has at least one legitimately failing test; if any target ID's tests all pass, or the only failures are illegitimate collection errors, it refuses.
- **DEV-SDD-004**: `green` advances only from `red`/`green`, and only when every test of every target ID passes.
- **DEV-SDD-005**: `verify` advances to `verified` only from `green`/`refactor`, and only when the gate command succeeds.
- **DEV-SDD-006**: `done` requires `verified`; it sets the spec status to `Implemented`, appends a `## Verification` entry with the IDs, red failures, green passes and gate result, ticks the IDs in `tasks.md`, and clears the state.
- **DEV-SDD-007**: The guard denies production edits unless the phase is `red`, `green`, `verified` or `refactor`, and the denial names the next command; a production edit while `verified` moves the phase to `green`.
- **DEV-SDD-008**: The guard denies test edits when no cycle is active, and allows them during any active cycle.
- **DEV-SDD-009**: The guard denies any agent edit (Edit or Write) that changes a spec's status to `Accepted` or `Implemented`.
- **DEV-SDD-010**: In refactor mode, production edits are allowed without a red phase, `done` still requires `verified`, the reason is recorded, and no spec is modified.
- **DEV-SDD-011**: The stop guard blocks the agent from ending its turn once when the phase is `red`, `green` or `verified`, naming the next command; it never blocks when the hook is already re-entered (`stop_hook_active`) or when no cycle is active.
- **DEV-SDD-012**: `spec:check` fails when a spec with status `Implemented` has no `## Verification` section.

## Security & privacy considerations

The guard is a guardrail against process drift, not a security boundary. An
agent with shell access can bypass it, and CI (spec coverage and verification
records) is the backstop.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · bootstrap, recorded by hand

This cycle built `sdd` itself, so it could not be run through `sdd`. Evidence
was observed manually. The status stays `Accepted` until a human sets
`Implemented`, the only case where that is done by hand.

- Criteria: DEV-SDD-001 … DEV-SDD-012
- Red: `scripts/tests/test_sdd.py` failed to import (`ModuleNotFoundError: No module named 'sdd'`), and `test_implemented_specs_need_a_verification_record` failed on its assertion
- Green: 40 passing test(s) in `scripts/tests`; live checks: real pytest red accepted for a missing `shield_engine` symbol and refused for a missing third-party module; the Edit guard denied a production edit with no cycle, and denied setting this spec to `Implemented`
- Gate: `mise run check` passed
