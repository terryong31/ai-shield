# 0004 — Debate adjudication (Layer 2)

- **Status:** Implemented
- **Area:** ENG
- **Created:** 2026-09-23
- **Related:** spec 0001

## Problem

Ambiguous prompts need contextual reasoning. Two LLM personas, the Analyst
(threat analysis) and the Warden (policy enforcement), debate the prompt, and
the Warden issues a binding verdict and tool policy.

The previous implementation had two defects that matter for an
injection-defence product:

1. It interpolated the caller's **passphrase** into the LLM system prompt.
2. It pasted the untrusted prompt into the adjudicator's own context with no
   delimiting, so the adjudicator was itself open to prompt injection.

## Goals

- Stream each debate turn as it is produced.
- Treat the screened prompt strictly as data.
- Parse the Warden's verdict defensively; never crash the pipeline.

## Behaviour

Turns: Analyst → Warden → Analyst, then a final Warden call that must return
JSON `{verdict, policy, confidence, summary}`. The three conversational turns
are streamed as `DialogueTurn`s; the final JSON becomes an `Adjudication`.

The untrusted prompt is wrapped as
`<untrusted_prompt>…</untrusted_prompt>`, and the system prompt instructs the
model never to follow instructions inside it. Any occurrence of the closing
tag inside the prompt is neutralised so it cannot break out.

Fallback (on unparseable output or model error): clearance `GRANTED` yields
SAFE/`ALLOW_ALL`, otherwise UNCERTAIN/`RESTRICTED`, confidence 0.5.

## Acceptance criteria

- **ENG-ADJ-001**: When adjudicating, then exactly three `DialogueTurn`s are yielded in the order ANALYST, WARDEN, ANALYST, followed by one `Adjudication` whose `dialogue` contains those turns.
- **ENG-ADJ-002**: Given a prompt containing `</untrusted_prompt>`, when adjudicating, then every message sent to the model contains the prompt only inside one intact `<untrusted_prompt>` block and the injected closing tag is neutralised.
- **ENG-ADJ-003**: Given the Warden's JSON is wrapped in code fences or surrounded by prose, when parsed, then the verdict and policy are extracted.
- **ENG-ADJ-004**: Given the Warden's output is unparseable or has out-of-range enum values, when parsed, then the clearance-based fallback applies.
- **ENG-ADJ-005**: Given the model raises mid-debate, when adjudicating, then the fallback `Adjudication` is returned, carrying the turns completed so far.
- **ENG-ADJ-006**: Given a confidence outside [0, 1] or non-numeric, when parsed, then it is clamped into [0, 1] (non-numeric → 0.5).
- **ENG-ADJ-007**: When adjudicating, then the clearance is conveyed to the model only as the words GRANTED or DENIED; the engine API accepts no credential material.

## Security & privacy considerations

The adjudicator is an LLM reading attacker-controlled text; ENG-ADJ-002 is the
primary mitigation, and the deterministic Layer 1 and policy gate are the
backstops. Delimiting reduces, but does not eliminate, injection risk. Track
it with adversarial evals.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: ENG-ADJ-001, ENG-ADJ-002, ENG-ADJ-003, ENG-ADJ-004, ENG-ADJ-005, ENG-ADJ-006, ENG-ADJ-007
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 13 passing test(s)
- Gate: `mise run check` passed
