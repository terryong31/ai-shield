# 0014 — Web audit view

- **Status:** Accepted
- **Area:** WEB
- **Owner:** Terry Ong
- **Created:** 2026-09-24
- **Related:** [spec 0011](../0011-web-product-redesign/spec.md) (design, copy, status language), [0011 plan](../0011-web-product-redesign/plan.md)

## Problem

The audit page cannot filter by action or review state, formats confidence inconsistently, and rewrites the enforcement `action` after a human review (`pages/dashboard/logs.vue:47`), so the table misreports what the shield did (spec 0011, Problem 2).

## Goals

- See [spec 0011, Goals](../0011-web-product-redesign/spec.md#goals). This spec is one slice of that redesign.

## Non-goals

- Anything outside the criteria below; the other slices have their own specs.

## Behaviour

As described in [spec 0011, Behaviour](../0011-web-product-redesign/spec.md#behaviour) and the
[0011 plan's Interfaces](../0011-web-product-redesign/plan.md#interfaces).

The gateway's `review()` overwrites `action` server-side in the same way. That is out of scope here and needs its own API spec.

## Acceptance criteria

- **WEB-AUDIT-001**: Given audit records, when `filterAuditRecords` runs with any combination of action (`ALLOWED`/`BLOCKED`/all), review state (reviewed/unreviewed/all) and free text, then only matching records are returned; free text matches query, reason and layer, case-insensitive.
- **WEB-AUDIT-002**: Given a record and a reviewer label, when `applyReview` runs, then `reviewed` and `human_label` are set, and `action`, `layer` and `reason` are unchanged.
- **WEB-AUDIT-003**: `formatConfidence` renders a number in [0, 1] as a percentage with one decimal, and renders `null`, `undefined`, `NaN` and non-numeric values as an em dash.

## Security & privacy considerations

No new data leaves the browser; all calls still go through `useShieldApi()`.

## Evaluation impact

None. No engine change.

## Open questions

None.
