---
name: new-spec
description: Draft a new specification in specs/ from a feature request or bug report, following this repo's spec-driven process. Use whenever a behaviour change is requested and no existing spec covers it.
---

# Draft a spec

1. **Check for an existing spec.** Read `specs/README.md` and grep `specs/` for the
   area. If a spec already covers the behaviour, propose new criteria for it instead
   of creating a new spec (new IDs only; never repurpose one).
2. **Scaffold**: `mise run spec:new <kebab-slug>`. This creates `spec.md`, `plan.md` and `tasks.md`.
3. **Understand the current behaviour** by reading the code and tests it touches.
   Record facts, not guesses.
4. **Fill in `spec.md`** (Status stays `Draft`):
   - Problem with evidence; goals; explicit non-goals.
   - Behaviour as tables and examples.
   - Acceptance criteria: `- **<AREA>-<COMP>-<NNN>**: Given …, when …, then …`.
     Pick the next free number for that component (grep to confirm uniqueness).
     Cover error paths and security failure modes.
   - Security & privacy, and evaluation impact for engine changes.
   - Put anything you could not decide under Open questions.
5. **For non-trivial work**, fill in `plan.md` (interfaces, boundaries checklist,
   alternatives) and `tasks.md` (one TDD cycle per criterion).
6. **Add a row** to the index table in `specs/README.md`.
7. **Review**: run the `spec-reviewer` subagent on the spec and address its findings.
8. **Stop.** Present the spec and the open questions to the human. Only a human
   moves a spec to `Accepted`; the SDD guard denies agents that try. Once it is
   accepted, implement it with `/tdd` (which starts with `mise run sdd:start`).
