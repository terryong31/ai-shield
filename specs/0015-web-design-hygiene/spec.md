# 0015 — Web design-system hygiene

- **Status:** Accepted
- **Area:** WEB
- **Owner:** Terry Ong
- **Created:** 2026-09-24
- **Related:** [spec 0011](../0011-web-product-redesign/spec.md) (design, copy, status language), [0011 plan](../0011-web-product-redesign/plan.md)

## Problem

Components hard-code Tailwind palette colours, glow shadows, `!important` overrides and hand-rolled controls (spec 0011, Problem 1). Without an automated check, these come back.

## Goals

- See [spec 0011, Goals](../0011-web-product-redesign/spec.md#goals). This spec is one slice of that redesign.

## Non-goals

- Anything outside the criteria below; the other slices have their own specs.

## Behaviour

As described in [spec 0011, Behaviour](../0011-web-product-redesign/spec.md#behaviour) and the
[0011 plan's Interfaces](../0011-web-product-redesign/plan.md#interfaces).

The checks are source scans over `apps/web/app/**/*.{vue,ts}`, excluding `types/api.gen.ts`. They land last, because they fail until slices 3–5 have replaced the old components.

## Acceptance criteria

- **WEB-UI-001**: No Tailwind palette colour utilities (for example `text-zinc-400`, `bg-rose-500/10`, `!bg-emerald-500`) appear; only Nuxt UI semantic tokens are used.
- **WEB-UI-002**: No native `<button>`, `<input>`, `<select>`, `<textarea>`, `<table>` or `<dialog>` elements appear; the Nuxt UI component is used instead.
- **WEB-UI-003**: No `!`-important utilities, arbitrary-value shadows (`shadow-[…]`) or `animate-pulse` appear.
- **WEB-UI-005**: `color="error"` (or `color: 'error'`) appears only on `UButton` elements, and each one belongs to an action in the dangerous-actions table.

## Security & privacy considerations

No new data leaves the browser; all calls still go through `useShieldApi()`.

## Evaluation impact

None. No engine change.

## Open questions

None.
