# 0001 — Screening pipeline

- **Status:** Implemented
- **Area:** ENG
- **Created:** 2026-09-23
- **Related:** [ADR 0002](../../docs/explanation/decisions/0002-engine-gateway-split.md), specs 0002–0005

## Problem

The detection logic lived inside the FastAPI chat route, interleaved with
HTTP streaming, Supabase logging and demo tool calls. It could not be
embedded in another application, evaluated offline, or unit-tested without a
web server.

## Goals

- A single `Shield` entry point that screens one prompt and returns a `Decision`.
- A streaming variant that emits typed events so a UI can show progress.
- All external services (LLMs, stores) are injected through ports.

## Non-goals

- Generating the assistant's answer or executing tools. That is the host
  application's job; the engine only decides *whether* and *with which tool
  policy* it may proceed.
- Authentication. The host resolves who the caller is and passes a `Clearance`
  level; the engine never sees credentials.

## Behaviour

```
prompt ─▶ L1 classifier ─▶ moderation (optional) ─▶ route
                                                    ├─ MALICIOUS ─────────────▶ BLOCK (LAYER_1_ML)
                                                    ├─ needs adjudication ─▶ L2 debate ─▶ BLOCK | ALLOW
                                                    └─ otherwise ──────────────▶ ALLOW (default policy)
```

Adjudication is required when any of these hold: the routed verdict is
`UNCERTAIN`, `always_adjudicate` is set, or the caller claimed clearance
(`GRANTED` or `DENIED`).

`ShieldConfig` controls routing only; classification thresholds belong to the
classifier (spec 0002). A per-call `config` overrides the instance default.

| Config | Default | Effect |
| --- | --- | --- |
| `always_adjudicate` | `False` | Debate every prompt ("guardrail" mode) |
| `skip_classifier` | `False` | Ablation: treat L1 as SAFE/0.0 ("chaos" mode) |
| `default_policy` | `ALLOW_ALL` | Tool policy when no adjudication ran |

Event stream, in order: `StageStarted(CLASSIFIER)`, `ClassifierScored`,
`ModerationFlagged` (only when flagged), then if adjudicating
`StageStarted(ADJUDICATION)` followed by zero or more `DebateTurn`s, then
exactly one terminal `DecisionMade`.

## Acceptance criteria

- **ENG-PIPE-001**: Given the classifier returns MALICIOUS, when a prompt is screened, then the decision is blocked at `LAYER_1_ML` with policy `SHUTDOWN` and the adjudicator is never invoked.
- **ENG-PIPE-002**: Given the classifier returns SAFE, no clearance and `always_adjudicate=False`, when screened, then the decision is allowed with `default_policy` and no adjudication runs.
- **ENG-PIPE-003**: Given the classifier returns UNCERTAIN, when screened, then the adjudicator runs and its verdict and policy become the decision.
- **ENG-PIPE-004**: Given the adjudicator returns MALICIOUS, when screened, then the decision is blocked at `LAYER_2_DUAL_AGENT` with policy `SHUTDOWN` regardless of the policy the adjudicator proposed.
- **ENG-PIPE-005**: Given moderation flags the prompt, when the classifier said SAFE, then routing escalates to UNCERTAIN (adjudication runs); when the classifier said MALICIOUS the decision stays a Layer 1 block.
- **ENG-PIPE-006**: Given `always_adjudicate=True`, when a SAFE prompt is screened, then adjudication runs.
- **ENG-PIPE-007**: Given clearance `GRANTED` or `DENIED`, when a SAFE prompt is screened, then adjudication runs and receives that clearance.
- **ENG-PIPE-008**: Given `skip_classifier=True`, when screened, then the classifier is not called, the L1 signal is SAFE with score 0.0 and `details.skipped=True`, and no Layer 1 block can occur.
- **ENG-PIPE-009**: Given adjudication is required but no adjudicator is configured, when screened, then a conservative fallback applies: clearance `GRANTED` yields SAFE/`ALLOW_ALL`, anything else yields UNCERTAIN/`RESTRICTED`, not blocked.
- **ENG-PIPE-010**: When a prompt is screened as a stream, then events arrive in the documented order and `DecisionMade` is emitted exactly once, last.
- **ENG-PIPE-011**: `Shield.screen()` returns the same `Decision` carried by the final `DecisionMade` event of `Shield.screen_stream()`.

## Security & privacy considerations

- The engine receives a `Clearance` enum, never a passphrase or token, so no
  credential can leak into LLM prompts or engine logs.
- The fallback in ENG-PIPE-009 is fail-*restricted*, not fail-open: without an
  adjudicator, uncleared callers lose access to non-LOW-risk tools.
- `default_policy=ALLOW_ALL` preserves the original demo behaviour. A
  deployment that wants deny-by-default tool access should set `RESTRICTED`.

## Evaluation impact

Pipeline-level metrics are measured by `mise run eval` (spec 0006).

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: ENG-PIPE-001, ENG-PIPE-002, ENG-PIPE-003, ENG-PIPE-004, ENG-PIPE-005, ENG-PIPE-006, ENG-PIPE-007, ENG-PIPE-008, ENG-PIPE-009, ENG-PIPE-010, ENG-PIPE-011
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 16 passing test(s)
- Gate: `mise run check` passed
