# 0013 — Web trace model

- **Status:** Accepted
- **Area:** WEB
- **Owner:** Terry Ong
- **Created:** 2026-09-24
- **Related:** [spec 0011](../0011-web-product-redesign/spec.md) (design, copy, status language), [0011 plan](../0011-web-product-redesign/plan.md)

## Problem

The stream reducer drops moderation results, keeps only the last debate turn and records no timing. The pipeline's node-status logic lives, untested, in a `watch` inside `WorkflowVisualizer.vue` (spec 0011, Problem 3).

## Goals

- See [spec 0011, Goals](../0011-web-product-redesign/spec.md#goals). This spec is one slice of that redesign.

## Non-goals

- Anything outside the criteria below; the other slices have their own specs.

## Behaviour

As described in [spec 0011, Behaviour](../0011-web-product-redesign/spec.md#behaviour) and the
[0011 plan's Interfaces](../0011-web-product-redesign/plan.md#interfaces).

## Acceptance criteria

- **WEB-TRACE-001**: Given a `WorkflowState`, when `derivePipelineGraph` runs, then it returns a status from the status-language table for every node (input, classifier, moderation, router, adjudication, assistant, tools, blocked), and the edges on the path taken so far are marked, for each of: idle; classifier running; SAFE; UNCERTAIN → debate running; UNCERTAIN → debate allowed; MALICIOUS blocked; blocked after debate; tools running.
- **WEB-TRACE-002**: Given a `LLAMAGUARD_RESULT` event, when folded by `applyChatEvent`, then the workflow records `moderation = { safe, categories }`, and the safety-check node is `flagged` with the categories as its datum. The gateway emits this event only when moderation flags a message, so with no event the node is `passed` once the decision is reached, or `skipped` in `chaos` mode.
- **WEB-TRACE-003**: Given several `DEBATE_TURN` events, when folded, then every turn is kept in order as `{ agent, message }` in `workflow.debate`, and the previous state is not mutated.
- **WEB-TRACE-004**: Given events folded with a timestamp `now`, when folded, then the `START` event records `startedAt = now` on the turn, and every event (including `START`) is appended to `workflow.timeline` as `{ type, at, summary }` with `at = now − startedAt`. Events folded without a timestamp are appended with `at = null`.
- **WEB-TRACE-005**: For every node status, `statusAppearance(status)` returns a non-empty icon and label, and no two statuses share the same icon and label.
- **WEB-TRACE-006**: Given a `BLOCK` event with a layer and reason, when folded, then the message text is `Blocked during <stage>. <reason>`, where the stages are `LAYER_1_ML` → `screening`, `LAYER_2_DUAL_AGENT` → `agent review`, `SYSTEM` → `system check`. The helper keeps the name `shutdownNotice`, so WEB-STREAM-004 (which compares against the helper) still holds; only the text changes.
- **WEB-TRACE-007**: The WEB-STREAM-001 … 005 tests from spec 0008 pass unchanged. `lastAgentMessage` stays on `WorkflowState` alongside the new `debate` list.

## Security & privacy considerations

No new data leaves the browser; all calls still go through `useShieldApi()`.

## Evaluation impact

None. No engine change.

## Open questions

None.
