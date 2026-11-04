# 0003 — Moderation detector (Llama Guard)

- **Status:** Implemented
- **Area:** ENG
- **Created:** 2026-09-23
- **Related:** spec 0001

## Problem

A second, independent opinion catches harms the Layer 1 classifier was never
trained on (MLCommons hazard taxonomy: violent crime, cyberattacks, PII, …).

## Goals

- Wrap any Llama Guard–style chat model behind the `ChatModel` port.
- Parse its `safe` / `unsafe\nS1,S13` output into a structured signal.
- Make the failure mode explicit and configurable.

## Behaviour

`moderate(text) -> ModerationResult(flagged, categories, raw, error)`.

Llama Guard answers `safe`, or `unsafe` followed by category codes on the next
line (comma- or newline-separated).

| `fail_closed` | On model error |
| --- | --- |
| `False` (default) | not flagged, `error` recorded |
| `True` | flagged with category `"ERROR"`, `error` recorded |

## Acceptance criteria

- **ENG-MOD-001**: Given the model answers `safe`, when moderated, then the result is not flagged and has no categories.
- **ENG-MOD-002**: Given the model answers `unsafe\nS1,S13` (or one code per line), when moderated, then the result is flagged with categories `["S1", "S13"]`.
- **ENG-MOD-003**: Given the model raises and `fail_closed=False`, when moderated, then the result is not flagged and `error` holds the exception message.
- **ENG-MOD-004**: Given the model raises and `fail_closed=True`, when moderated, then the result is flagged with category `ERROR`.

## Security & privacy considerations

Default fail-open keeps the demo responsive when Groq is unavailable; it is
safe *only* because moderation can escalate but never allow on its own. A
deployment that relies on moderation as its main control should set
`fail_closed=True`.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: ENG-MOD-001, ENG-MOD-002, ENG-MOD-003, ENG-MOD-004
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 6 passing test(s)
- Gate: `mise run check` passed
