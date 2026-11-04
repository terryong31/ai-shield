# 0008 — Web stream client

- **Status:** Implemented
- **Area:** WEB
- **Created:** 2026-09-23
- **Related:** spec 0007, [ADR 0005](../../docs/explanation/decisions/0005-ndjson-event-stream.md)

## Problem

Stream parsing and state updates were embedded in a 250-line Vue component,
so none of the protocol handling could be tested.

## Goals

- Pure, framework-free functions for NDJSON parsing and for folding events
  into UI state, unit-tested with Vitest.

## Behaviour

`splitNdjson(buffer)` returns complete lines and the trailing partial line.
`applyChatEvent(state, event)` returns the next workflow + message state.

## Acceptance criteria

- **WEB-STREAM-001**: Given a buffer whose last line is incomplete, when split, then complete lines are returned and the partial line is kept as the remainder.
- **WEB-STREAM-002**: Given blank lines or `\n\n` separators, when split, then no empty events are produced.
- **WEB-STREAM-003**: `ML_RESULT` sets confidence and verdict; `DEBATE_TURN` sets the last agent message and marks debate triggered; `POLICY_UPDATE` sets the policy; `TOOL_START` appends the tool; `STAGE_CHANGE` sets the stage.
- **WEB-STREAM-004**: `BLOCK` marks the workflow and message blocked and sets the message text to the shutdown notice with the reason; `FINAL_RESPONSE` and `ERROR` set the message text.
- **WEB-STREAM-005**: Given a line that is not valid JSON, when parsed, then it is reported as an error and parsing continues with the next line.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: WEB-STREAM-001, WEB-STREAM-002, WEB-STREAM-003, WEB-STREAM-004, WEB-STREAM-005
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 8 passing test(s)
- Gate: `mise run check` passed
