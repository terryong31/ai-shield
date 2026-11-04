# Specifications

Every behavioural change to AI S.H.I.E.L.D. starts here. We use
**spec-driven development** (the spec says *what* and *why*) together with
**test-driven development** (a failing test proves each acceptance criterion
before any code is written).

```
spec (Draft) ──human review──▶ Accepted ──sdd:start → sdd:red → sdd:green → sdd:verify → sdd:done──▶ Implemented
                                                                                             └─ ## Verification record appended
```

The cycle is enforced by `scripts/sdd.py` and Claude Code hooks
([spec 0010](0010-enforced-sdd-tdd-workflow/spec.md)); see AGENTS.md for the commands.

## Layout

Each feature gets a numbered folder:

```
specs/
├── _templates/            # copy these, never edit in place
│   ├── spec.md            # what + why + acceptance criteria   (required)
│   ├── plan.md            # how: design, interfaces, risks     (for non-trivial work)
│   └── tasks.md           # ordered TDD checklist              (for non-trivial work)
└── 0001-screening-pipeline/
    └── spec.md
```

Number folders sequentially (`0009-…`). Never renumber or reuse a number;
superseded specs stay in place with `Status: Superseded by 00NN`.

## Acceptance criteria and IDs

Criteria are written as observable behaviour, each with a stable ID:

```markdown
- **ENG-PIPE-001** — Given the classifier returns MALICIOUS, when the prompt is
  screened, then the decision is blocked at `LAYER_1_ML` and the adjudicator is
  never invoked.
```

ID format: `<AREA>-<COMPONENT>-<NNN>`.

| Area | Scope |
| --- | --- |
| `ENG` | `packages/engine`, the deflector engine |
| `API` | `apps/api`, the demo gateway |
| `WEB` | `apps/web`, the demo client |
| `DEV` | repository tooling and the development workflow |

IDs are permanent. If a criterion changes meaning, retire the ID and add a new one.

## Traceability rule (enforced in CI)

For every spec whose status is `Accepted` or `Implemented`, each criterion ID
must appear in at least one test:

- Python: `@pytest.mark.spec("ENG-PIPE-001")`
- TypeScript: put the ID in the test name: `it('[WEB-STREAM-001] keeps partial lines', …)`

Check locally with `mise run spec:check`.

## Status lifecycle

| Status | Meaning |
| --- | --- |
| `Draft` | Being written; not yet binding. Not checked for coverage. |
| `Accepted` | Reviewed and approved **by a human** (agents may not set it). Tests must exist for every criterion. |
| `Implemented` | All criterion tests pass on `main`, and a `## Verification` record exists (written by `mise run sdd:done`; CI checks it). |
| `Superseded by 00NN` | Kept for history. |

## Index

| # | Spec | Area | Status |
| --- | --- | --- | --- |
| 0001 | [Screening pipeline](0001-screening-pipeline/spec.md) | ENG | Implemented |
| 0002 | [Classifier detector](0002-classifier-detector/spec.md) | ENG | Implemented |
| 0003 | [Moderation detector](0003-moderation-detector/spec.md) | ENG | Implemented |
| 0004 | [Debate adjudication](0004-debate-adjudication/spec.md) | ENG | Implemented |
| 0005 | [Tool policy](0005-tool-policy/spec.md) | ENG | Implemented |
| 0006 | [Evaluation harness](0006-evaluation-harness/spec.md) | ENG | Implemented |
| 0007 | [Gateway HTTP API](0007-gateway-http-api/spec.md) | API | Implemented |
| 0008 | [Web stream client](0008-web-stream-client/spec.md) | WEB | Implemented |
| 0009 | [Audit log storage backends](0009-audit-log-storage/spec.md) | API | Implemented |
| 0010 | [Enforced SDD + TDD workflow](0010-enforced-sdd-tdd-workflow/spec.md) | DEV | Accepted (awaiting human sign-off) |
| 0011 | [Web product redesign](0011-web-product-redesign/spec.md) | WEB | Draft |
| 0012 | [Clearance sessions](0012-clearance-sessions/spec.md) | API | Implemented |
| 0013 | [Web trace model](0013-web-trace-model/spec.md) | WEB | Accepted |
| 0014 | [Web audit view](0014-web-audit-view/spec.md) | WEB | Accepted |
| 0015 | [Web design-system hygiene](0015-web-design-hygiene/spec.md) | WEB | Accepted |
| 0016 | [AI Defender workflow game](0016-game-engine/spec.md) | ENG, API, WEB | Implemented |
| 0017 | [Game gateway API](0017-game-api/spec.md) | API | Superseded by 0016 |
| 0018 | [Web Defender game](0018-game-web/spec.md) | WEB | Superseded by 0016 |

See [docs/how-to/write-a-spec.md](../docs/how-to/write-a-spec.md) for the
step-by-step workflow and [docs/explanation/development-process.md](../docs/explanation/development-process.md)
for why we work this way.
