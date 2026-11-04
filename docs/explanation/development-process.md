# Development process

Every behaviour change in this repository starts as a written specification
with numbered acceptance criteria, and every criterion is proven by a test that
was seen to fail before the code was written. This page explains why.
The decision is recorded in [ADR 0003](decisions/0003-spec-driven-and-test-driven-development.md);
the mechanics are in [`specs/README.md`](../../specs/README.md) and
[Write a spec](../how-to/write-a-spec.md).

## Why specs

A prompt-injection defence is judged by behaviour at its edges: what happens
when the classifier is unsure, when a provider times out, when the caller
claims clearance and gets it wrong. Those edges are exactly what gets lost
when a change goes straight from an idea to code. A spec forces them to be
decided, in words, before anyone is invested in an implementation:

- **Problem with evidence** keeps work tied to something observed: a prompt
  that got through, an eval number, a bug.
- **Non-goals** stop scope creep and pre-empt review comments.
- **Security & privacy** asks for the failure mode (fail-open, fail-closed,
  fail-restricted) and its rationale every time. The routing and fallback rules
  in [Defense in depth](defense-in-depth.md) came out of these sections.
- **Evaluation impact** asks for before/after numbers for detection changes,
  so claims of improvement are measured.

Specs are also cheap to review. Disagreement about behaviour is resolved on a
page of prose, not in a diff.

## Why tests first

A test written after the code tends to check what the code does. A test
written first, from the criterion, checks what the spec says, and seeing it
fail proves it can detect the absence of the behaviour. For a security control
that matters: a test that would pass whether or not the fix is present is
worse than none, because it creates false confidence.

The engine's ports make test-first practical. Every external dependency is a
`Protocol`, and `shield_engine.testing` ships deterministic doubles, so a
criterion like "given the adjudicator raises mid-debate, the fallback carries
the turns completed so far" is a few lines with a `ScriptedChatModel` whose
second reply is an exception. No network, no mocks of internals.

## How IDs create traceability

Each criterion has a permanent ID of the form `<AREA>-<COMPONENT>-<NNN>`, such
as `ENG-PIPE-004`. The same string appears:

- in the spec, as `- **ENG-PIPE-004**: Given …`
- on the test, as `@pytest.mark.spec("ENG-PIPE-004")` or `it('[WEB-STREAM-004] …')`
- in code review, pull request descriptions and commit messages

So you can go from a requirement to the tests that prove it with one `grep`,
and from a failing test back to the requirement it protects. When a test fails,
its ID tells you which promise broke and where the reasoning behind it lives.

IDs are never reused or renumbered. If a criterion's meaning changes, it gets a
new ID, so an old reference can never silently point at a different requirement.

## How CI enforces it

The rules are checked by machines, not by memory:

| Check | Enforced by | CI job |
| --- | --- | --- |
| Every criterion in an `Accepted` or `Implemented` spec is referenced by at least one test | `mise run spec:check` ([`scripts/check_spec_coverage.py`](../../scripts/check_spec_coverage.py)) | Specs & contract |
| Every `Implemented` spec carries a `## Verification` record (written by `mise run sdd:done`) | `mise run spec:check` | Specs & contract |
| The tests pass, with coverage floors (engine 90%, gateway 85%) | `mise run test:engine`, `test:api`, `test:web` | Python, Web |
| The committed HTTP contract and generated client match the code | `mise run contract:check` and the `API-CONTRACT-001` test | Specs & contract, Python |
| Lint and strict type checks | `mise run lint:*`, `typecheck:*` | Python, Web |
| Detection metrics are recorded | `mise run eval`, uploaded as the `eval-report` artifact | Engine benchmark |

`mise run check` runs the same gate locally
([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs the pieces in parallel jobs).

The status lifecycle keeps the check honest without blocking drafting: `Draft`
specs are not checked, so a spec can be written and reviewed before any test
exists. Once `Accepted`, missing tests fail CI. A red test is acceptable on a
branch mid-TDD, but `main` must be green.

Locally, the order of work is enforced too. `scripts/sdd.py` runs each
change as a cycle (spec → red → green → verified → done), and every transition
checks evidence: `sdd:red` actually runs the criterion's tests and refuses if
they pass or are merely broken, and `sdd:verify` runs the whole gate. Claude
Code hooks lock production code until red is proven and stop agents from
accepting their own specs ([spec 0010](../../specs/0010-enforced-sdd-tdd-workflow/spec.md)).
CI cannot see the red step after the fact; the verification record in the spec
is its trace.

Note what the check does not do. `spec:check` only confirms that an ID string
appears in a test file; it cannot judge whether the test actually proves the
criterion. That is what review is for.

## How it fits AI-assisted development

Coding agents are fast and literal. Given a vague request, they produce
plausible code that does something close to what was asked, with tests that
confirm whatever they built. The spec-driven loop turns that around:

- **The spec is the agent's contract.** A human accepts it; the agent
  implements exactly its criteria. Scope is visible and bounded.
- **IDs make agent output auditable.** Each test the agent writes names the
  criterion it proves; a reviewer can check the mapping one line at a time.
- **Red-first catches hollow tests.** An agent must show each test failing
  before implementing, which is harder to fake than a green run.
- **The gate is the same for everyone.** Agents run `mise run check`, as CI does.
  They are told never to weaken a test to pass it.
- **Acceptance stays human.** Agents may draft and review specs, but only a
  person moves a spec from `Draft` to `Accepted`
  ([`AGENTS.md`](../../AGENTS.md)).

The repository encodes this loop as Claude Code skills and subagents; see
[Work with AI agents](../how-to/work-with-ai-agents.md).

## Costs

The process has overhead: a one-line change still needs a criterion and a test.
Pure refactors, documentation and dependency bumps are exempt, and small changes
can use a spec without `plan.md` or `tasks.md`. The trade is deliberate: for a
security component, the cost of an unexamined edge case is higher than the cost
of writing it down.
