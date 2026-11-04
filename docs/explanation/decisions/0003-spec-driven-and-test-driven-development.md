# 0003. Spec-driven and test-driven development

- **Status:** Accepted
- **Date:** 2026-09-23

## Context

Security behaviour in this system is defined by edge cases: provider failures,
uncertain scores, wrong passphrases, malformed LLM output. Several defects in
the previous code were edge cases nobody had written down, such as the
passphrase being interpolated into an LLM prompt and a destructive demo tool
labelled low risk. The project also expects much of its code to be written with
AI coding agents, which implement what they are told literally and tend to write
tests that confirm their own output.

## Decision

- Every behaviour change starts with a spec in `specs/NNNN-slug/spec.md`, using
  the templates in `specs/_templates/`, with acceptance criteria that have
  permanent IDs (`<AREA>-<COMPONENT>-<NNN>`).
- Specs move through `Draft`, `Accepted`, `Implemented` (or `Superseded by NNNN`).
  Only a human accepts a spec.
- Each criterion is implemented test-first: a failing test tagged with the ID
  (`@pytest.mark.spec("ID")` or `[ID]` in a Vitest name), then code, then refactor.
- `scripts/check_spec_coverage.py` (`mise run spec:check`) fails CI if any
  criterion of an `Accepted` or `Implemented` spec is not referenced by a test.
- Detection changes record before/after `mise run eval` numbers in the spec.

## Consequences

- Requirements are traceable to tests by `grep`, in both directions.
- Review happens earlier and more cheaply, on behaviour rather than diffs.
- AI agents get a bounded, human-approved contract; their output can be audited
  criterion by criterion. The loop is encoded in `AGENTS.md` and Claude Code
  skills.
- Small changes carry overhead. Pure refactors, docs and dependency bumps are
  exempt.
- The coverage check only proves an ID appears in a test file, not that the
  test is meaningful. Review remains necessary.
