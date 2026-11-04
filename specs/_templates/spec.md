# NNNN — <Feature name>

- **Status:** Draft
- **Area:** ENG | API | WEB
- **Owner:** <name>
- **Created:** YYYY-MM-DD
- **Related:** <links to ADRs, issues, other specs>

## Problem

What is wrong or missing today, and who is affected? One or two paragraphs.
Link evidence (bug reports, eval results, user feedback).

## Goals

- What this change must achieve, stated as outcomes.

## Non-goals

- What is explicitly out of scope, so reviewers don't ask for it.

## Behaviour

Describe the behaviour from the outside: inputs, outputs, states, errors.
Prefer tables and examples over prose. No implementation detail here; that
goes in `plan.md`.

## Acceptance criteria

Each criterion is observable, testable, and has a permanent ID.

- **AREA-COMP-001**: Given …, when …, then ….
- **AREA-COMP-002**: Given …, when …, then ….

## Security & privacy considerations

Threats introduced or mitigated, data handled, failure modes (fail-open vs
fail-closed) and why.

## Evaluation impact

For engine changes: which benchmark metrics are expected to move, and the
command that measures them (`mise run eval`). Attach before/after numbers
before moving to `Implemented`.

## Open questions

- Anything unresolved. A spec cannot be `Accepted` while this list is non-empty.
