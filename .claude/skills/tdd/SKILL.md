---
name: tdd
description: Implement an Accepted spec with the enforced SDD cycle (start → failing tests → sdd:red → code → sdd:green → sdd:verify → sdd:done). Use when asked to implement, build or fix anything covered by a spec in specs/.
---

# Implement a spec (enforced SDD + TDD cycle)

Hooks enforce this order. If a tool call is denied with `[SDD]`, follow the
message; do not work around it (no shell writes, no editing `.sdd/`).

1. **Check the spec.** It must be `Accepted` (or `Implemented`, when fixing a
   bug against it). If it is `Draft` or missing, stop and use `/new-spec`.
   Never change a spec's status yourself.
2. **Start**: `mise run sdd:start <NNNN>`. To work in slices, name the IDs:
   `mise run sdd:start 0012 ENG-X-003 ENG-X-004`.
3. **Write the tests only** (or delegate to the `test-author` subagent). Tag
   each one: `@pytest.mark.spec("ID")`, or `[ID]` at the start of the Vitest
   name. Use `shield_engine.testing` fakes; no network.
4. **Prove red**: `mise run sdd:red`. It refuses if a criterion has no test,
   if a test already passes, or if a failure is a broken test rather than
   missing behaviour. Fix the tests until it accepts.
5. **Implement** the minimum production code. Respect the boundaries in `AGENTS.md`.
   - HTTP shapes changed: `mise run contract`, then update the web client.
   - Detection changed: `mise run eval` before and after, and record both in the spec.
   - Schema changed: `mise run db:migration <name>`, and mirror the columns in `SqliteAuditLog`.
6. **Green**: `mise run sdd:green`. Iterate until it passes. Refactor with the tests green.
7. **Docs**: update `docs/reference/…` and `CHANGELOG.md` (`## [Unreleased]`).
8. **Verify**: `mise run sdd:verify` runs `mise run check`. Fix everything it reports.
9. **Review**: run the `code-reviewer` subagent and fix Blocking findings. If
   you changed code, run `mise run sdd:verify` again.
10. **Done**: `mise run sdd:done`. Report to the user: the criteria, test names,
    the red and green evidence, and the verification entry added to the spec.
