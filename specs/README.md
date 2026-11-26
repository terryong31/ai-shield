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
| 0001 | [Screening pipeline](0001-screening-pipeline/spec.md) | ENG | Superseded by 0026 |
| 0002 | [Classifier detector](0002-classifier-detector/spec.md) | ENG | Implemented |
| 0003 | [Moderation detector](0003-moderation-detector/spec.md) | ENG | Superseded by 0026 |
| 0004 | [Debate adjudication](0004-debate-adjudication/spec.md) | ENG | Superseded by 0026 |
| 0005 | [Tool policy](0005-tool-policy/spec.md) | ENG | Superseded by 0026 |
| 0006 | [Evaluation harness](0006-evaluation-harness/spec.md) | ENG | Superseded by 0026 |
| 0007 | [Gateway HTTP API](0007-gateway-http-api/spec.md) | API | Implemented |
| 0008 | [Web stream client](0008-web-stream-client/spec.md) | WEB | Superseded by 0026 |
| 0009 | [Audit log storage backends](0009-audit-log-storage/spec.md) | API | Superseded by 0026 |
| 0010 | [Enforced SDD + TDD workflow](0010-enforced-sdd-tdd-workflow/spec.md) | DEV | Accepted (awaiting human sign-off) |
| 0011 | [Web product redesign](0011-web-product-redesign/spec.md) | WEB | Superseded by 0026 |
| 0012 | [Clearance sessions](0012-clearance-sessions/spec.md) | API | Implemented |
| 0013 | [Web trace model](0013-web-trace-model/spec.md) | WEB | Superseded by 0026 |
| 0014 | [Web audit view](0014-web-audit-view/spec.md) | WEB | Superseded by 0026 |
| 0015 | [Web design-system hygiene](0015-web-design-hygiene/spec.md) | WEB | Accepted |
| 0016 | [AI Defender workflow game](0016-game-engine/spec.md) | ENG, API, WEB | Implemented |
| 0017 | [Game gateway API](0017-game-api/spec.md) | API | Superseded by 0016 |
| 0018 | [Web Defender game](0018-game-web/spec.md) | WEB | Superseded by 0016 |
| 0020 | [Game AI Agent, scoring and run quotas](0020-game-ai-agent/spec.md) | ENG, API, WEB | Implemented |
| 0021 | [Game level tiers](0021-game-level-tiers/spec.md) | ENG, API, WEB | Implemented |
| 0022 | [Custom sandbox (BYOD, BYOK)](0022-game-custom-sandbox/spec.md) | ENG, API, WEB | Implemented |
| 0023 | [Saved boards](0023-game-saved-boards/spec.md) | API, WEB | Implemented |
| 0024 | [Domain-scoped database schemas (`audit`, `game`, `players`)](0024-domain-schema-storage/spec.md) | API | Implemented |
| 0025 | [Account settings](0025-account-settings/spec.md) | API, WEB | Implemented |
| 0029 | [Strict win/lose and tool configuration](0029-strict-win-lose-and-tool-config/spec.md) | ENG, API, WEB | Implemented |
| 0030 | [Tool refinements and Jev](0030-tool-refinements-and-jev/spec.md) | ENG, API, WEB | Implemented |
| 0031 | [Live Jev & AI node API keys and real measured latency/cost](0031-live-api-keys-and-real-metrics/spec.md) | ENG, API, WEB | Implemented |
| 0032 | [System .env-only API keys](0032-env-only-api-keys/spec.md) | API, WEB | Accepted |
| 0033 | [Saved board return check and instant loading state](0033-saved-board-return-and-loading/spec.md) | WEB | Implemented |
| 0034 | [Distinct Safety check vs Agent review](0034-safety-vs-agent-review-models/spec.md) | ENG, API, WEB | Implemented |
| 0035 | [Merge Quick screen into ML filter](0035-merge-quick-screen-into-ml-filter/spec.md) | ENG, API, WEB | Implemented |
| 0036 | [Password strength indicator and validation](0036-password-strength-validation/spec.md) | API, WEB | Implemented |
| 0037 | [LangGraph AI Agent and Tool Policy extension](0037-langgraph-agent-and-tool-policy/spec.md) | ENG, API, WEB | Implemented |
| 0038 | [ML filter user-defined training data only](0038-ml-classifier-user-data-only/spec.md) | ENG, API, WEB | Implemented |
| 0039 | [Campaign levels and difficulty leaderboard](0039-campaign-levels-and-difficulty-leaderboard/spec.md) | ENG, API | Implemented |
| 0040 | [Minimal monochrome Level Select and in-game briefing UI](0040-campaign-problem-hub-and-briefing-ui/spec.md) | WEB | Implemented |
| 0028 | [Instant leaderboard](0028-instant-leaderboard/spec.md) | API, WEB | Superseded by 0044 |
| 0026 | [Game-only cleanup](0026-game-only-cleanup/spec.md) | ENG, API, WEB | Implemented |
| 0027 | [Player email confirmation](0027-player-email-confirmation/spec.md) | API, WEB | Implemented |
| 0041 | [Same-origin API proxy](0041-same-origin-api-proxy/spec.md) | WEB | Implemented |
| 0042 | [Run spend and account integrity](0042-run-spend-and-account-integrity/spec.md) | API, WEB | Implemented |
| 0043 | [Rate limiting, trusted client IP, bot protection and production configuration](0043-rate-limiting-and-client-ip/spec.md) | API, WEB | Implemented |
| 0044 | [Leaderboard on Redis sorted sets](0044-leaderboard-read-scaling/spec.md) | API, WEB | Implemented |
| 0045 | [Training upload hardening and server-held models](0045-train-upload-hardening/spec.md) | ENG, API, WEB | Implemented |
| 0046 | [Remove SQLite: Supabase is the only store](0046-remove-sqlite-supabase-only/spec.md) | API, DEV | Implemented |
| 0047 | [Auth flows and hardening](0047-auth-flows-and-hardening/spec.md) | API, WEB | Implemented |
| 0048 | [Display name](0048-display-name/spec.md) | API, WEB | Implemented |
| 0049 | [Stripe pass checkout (sandbox)](0049-stripe-pass-checkout/spec.md) | API, WEB | Implemented |
| 0050 | [Fair scoring and the scored run](0050-campaign-redesign/spec.md) | ENG, API, WEB | Implemented |
| 0051 | [Campaign levels v2](0051-campaign-levels-v2/spec.md) | ENG, API, WEB | Draft |

See [docs/how-to/write-a-spec.md](../docs/how-to/write-a-spec.md) for the
step-by-step workflow and [docs/explanation/development-process.md](../docs/explanation/development-process.md)
for why we work this way.
