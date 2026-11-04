# Write a spec

The rules (ID format, status meanings, traceability) are defined in
[`specs/README.md`](../../specs/README.md). This page is the checklist for
applying them.

## When you need one

| Change | Spec |
| --- | --- |
| New behaviour, changed behaviour, new config that changes behaviour | yes |
| Bug fix | a failing test first, linked to an existing criterion or a new one |
| HTTP contract change | yes (criteria in spec 0007 or a new spec) |
| Pure refactor, docs-only, dependency bump | no; existing tests must stay green |

First check whether an existing spec covers the area (see the index in
`specs/README.md`). If so, add new criteria to it rather than creating a new spec.

## 1. Scaffold

```bash
mise run spec:new <kebab-case-slug>
```

Creates `specs/NNNN-<slug>/` with `spec.md`, `plan.md` and `tasks.md` from
`specs/_templates/`, numbered with the next free number and dated today.
Delete `plan.md` and `tasks.md` for trivial changes; keep them for anything
that touches interfaces or several modules.

Add a row to the index table in `specs/README.md`.

## 2. Fill in `spec.md`

- [ ] Header: `Status: Draft`, `Area` (`ENG`, `API` or `WEB`), `Owner`, `Related` links.
- [ ] **Problem** with evidence: a failing prompt, an eval number, a bug report.
- [ ] **Goals** as outcomes, **Non-goals** explicit.
- [ ] **Behaviour** from the outside, as tables and examples. No implementation detail.
- [ ] **Acceptance criteria**, one behaviour each, in this exact form (the
      coverage script matches `- **ID**` at the start of a line):

      ```markdown
      - **ENG-CLS-008**: Given …, when …, then ….
      ```

- [ ] Cover the error paths, empty inputs and the failure mode (fail-open,
      fail-closed or fail-restricted, and why).
- [ ] **Security & privacy**: new inputs, trust boundaries, data stored, secrets.
- [ ] **Evaluation impact** (engine changes): which metric should move, measured
      with `mise run eval`.
- [ ] **Open questions**: must be empty before acceptance.

## 3. Choose IDs

- Format `<AREA>-<COMPONENT>-<NNN>`: 2–5 capital letters, 2–10 capital letters,
  three digits (for example `API-CHAT-007`).
- Reuse the component name an existing spec uses for the same component and
  take the next number.
- IDs are global and permanent. Check uniqueness before using one:

  ```bash
  grep -rn "API-CHAT-007" specs packages apps
  ```

- If a criterion changes meaning, retire its ID and add a new one. Never reuse
  or renumber.

## 4. Fill in `plan.md` and `tasks.md` (non-trivial work)

- `plan.md`: approach, changed interfaces (mark breaking changes), the
  boundaries checklist, alternatives, rollback.
- `tasks.md`: one line per criterion, each a red/green/refactor cycle and ideally one commit.

## 5. Review

- [ ] Open a pull request containing only the spec, or ask for review before coding.
- [ ] If you use Claude Code, run the `spec-reviewer` subagent first
      ([Work with AI agents](work-with-ai-agents.md)).
- [ ] Reviewers check: problem is real, criteria are testable and complete,
      no boundary is broken, open questions are empty.
- [ ] A human sets `Status: Accepted`. Agents never do.

## 6. Implement and close

Once `Accepted`, `mise run spec:check` requires every criterion ID to appear in a test:

- Python: `@pytest.mark.spec("ENG-CLS-008")`
- Vitest: the ID in brackets in the test name, `it('[WEB-STREAM-006] …', …)`

Implement through the enforced cycle (see [work with AI agents](work-with-ai-agents.md#the-loop)):

```bash
mise run sdd:start NNNN      # spec must be Accepted
# write the tagged tests
mise run sdd:red             # proves they fail
# implement
mise run sdd:green           # proves they pass
mise run sdd:verify          # full gate
mise run sdd:done            # sets Implemented and appends ## Verification
```

Before `sdd:done`:

- [ ] Reference docs in `docs/reference/` updated.
- [ ] Engine changes: before/after `mise run eval` numbers in "Evaluation impact".
- [ ] The index row in `specs/README.md` says `Implemented`.

Don't set `Implemented` by hand. `spec:check` rejects `Implemented` specs
that have no `## Verification` record.

## Superseding

To replace a spec, create a new one and set the old one's status to
`Superseded by 00NN`. Superseded specs are not checked for coverage and stay in
place for history.

## Related

- [Tutorial 3: Your first spec-driven change](../tutorials/03-your-first-spec-driven-change.md)
- [Development process](../explanation/development-process.md)
