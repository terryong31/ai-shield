# 0011 — Web product redesign

- **Status:** Draft
- **Area:** WEB
- **Owner:** Terry Ong
- **Created:** 2026-09-24
- **Related:** spec 0008, [ADR 0004](../../docs/explanation/decisions/0004-frontend-talks-only-to-gateway.md), [plan.md](plan.md), [tasks.md](tasks.md)

## Problem

`apps/web` works, but it reads as a generated demo rather than a product.
An audit of every file in `apps/web/app` found four kinds of problem.

**1. The styling bypasses the design system.** Every pipeline node
hard-codes Tailwind palette colours (`text-emerald-400`, `bg-zinc-900/90`,
`!bg-rose-500`), glow shadows (`shadow-[0_0_15px_rgba(59,130,246,0.4)]`),
`animate-pulse` and `!important` overrides
(`components/workflow/NodeContainer.vue:9-20`, all `*Node.vue`). Chips are
hand-rolled `<span>`s where `UBadge` exists (`ToolboxNode.vue:32`,
`SwitchNode.vue:35`). Seven node components repeat the same `Handle`,
icon and title markup. The palette mixes blue, emerald, rose, amber, cyan
and zinc with no system behind it. Status is shown only by colour, which
fails for colour-blind users.

**2. The UI states things that are not true.** The Overview's "Defense
Pipeline Status" card hard-codes `ACTIVE / READY / STANDBY` and model names
("Groq Llama 3.3 70B") that come from no API (`DashboardPipeline.vue:3-21`).
After a reviewer labels a prompt, the audit table rewrites the record's
enforcement `action` to match the label (`pages/dashboard/logs.vue:47`), so
the table no longer shows what the shield actually did. The "RLHF Feedback"
column is a human label, not RLHF.

**3. The shield's work is mostly invisible.** Moderation results
(`LLAMAGUARD_RESULT`) are dropped (`utils/chatStream.ts:84`) and have no
node. Only the last debate turn survives (`chatStream.ts:59`), so the
Analyst/Warden transcript is lost. Nodes cannot be clicked. The audit log has
no detail view, so `reason` and `metadata` cannot be read. The console opens
on an empty screen with no guidance.

**4. The copy and structure feel generated.** "Oblivion", "Threats
Neutralized", "Calculated platform threat index", "Enterprise Navbar",
"[SHUTDOWN PROTOCOL TRIGGERED]". There are two unrelated layouts (a
hand-built header in `layouts/default.vue` and a `UDashboardGroup` in
`layouts/dashboard.vue`). The passphrase modal lives in `app.vue`, and the
passphrase is stored in plaintext in `localStorage`. There is no favicon,
no page titles, no error page and no light theme (`nuxt.config.ts` forces
dark).

## Goals

- A distinctive, professional, **monochrome** interface. Status is carried by
  shape, fill, line style, icon and label, never by hue. The one exception is
  buttons for dangerous actions, which use the `error` colour (red).
- Plain, professional wording in Malaysian English: British spelling
  (colour, analyse, authorise), short sentences, everyday words, and no
  sci-fi or military terms.
- Nuxt UI components and semantic tokens everywhere; no raw palette colours,
  no hand-rolled equivalents of Nuxt UI components.
- Every value on screen comes from the gateway or is clearly labelled as
  static documentation.
- The full trace of a request (classifier, moderation, router, debate, policy,
  tools) can be inspected, both as a graph and as a timeline.
- One application shell, working in light and dark mode, keyboard-navigable.

## Non-goals

- HTTP contract changes. If a real pipeline-health endpoint is wanted, that is
  a separate API spec.
- Authentication and multi-user accounts.
- Changing detection behaviour in `packages/engine`.
- Mobile-first layouts. Console and audit must be usable at 1024px and not
  break at 375px, but they are desktop tools.

## Behaviour

### Information architecture

| Route | Page | Replaces |
| --- | --- | --- |
| `/` | **Console**: chat + live trace (Graph and Timeline tabs, node inspector) | `/` |
| `/overview` | Totals, block rate and an explanation of the pipeline (labelled static) | `/dashboard` |
| `/audit` | Audit log: filterable table, record detail slideover, reviewer labels | `/dashboard/logs` |
| `/settings` | Operating mode, clearance, appearance | `/dashboard/settings` |

All pages share one `UDashboardGroup` shell with a collapsible sidebar.

### Monochrome status language

| Node status | Treatment | Icon | Label |
| --- | --- | --- | --- |
| `idle` | dashed hairline border, dimmed text | none | "Idle" |
| `active` | solid border, animated dashed edge into the node | spinner | "Running" |
| `passed` | solid border, default text | check | "Passed" |
| `flagged` | solid border, diagonal hatch fill | alert | "Flagged" |
| `blocked` | inverted: `bg-inverted` / `text-inverted` | shield-x | "Blocked" |
| `skipped` | dashed border, 50% opacity | minus | "Skipped" |

### Dangerous actions

A dangerous action is one that removes protection, removes access or
discards data. These are the only elements allowed a hue, and they use
`UButton color="error"`:

| Action | Where |
| --- | --- |
| Revoke admin access | Admin access dialog, Settings |
| Switch to "No protection" | Confirmation dialog in Settings |
| Clear conversation | Console header |

Everything else, including "Mark as harmful", uses neutral colours.

### Copy

| Where | Current | New |
| --- | --- | --- |
| Node | User Prompt | Message |
| Node | Layer 1: ML Engine | Screening |
| Node | (none) | Safety check |
| Node | Policy Router | Decision |
| Node | Layer 2: Dual Agents / Analyst & Warden Debate | Agent review (Analyst and Warden) |
| Node | Primary Assistant | Assistant |
| Node | Toolbox Execution | Tools used |
| Node | Oblivion (Blocked) | Blocked |
| Tool policy | `ALLOW_ALL` / `RESTRICTED` / `SHUTDOWN` | All tools / Limited tools / No tools |
| Mode | AI S.H.I.E.L.D. (Standard Dual-Layer) | **Standard protection**: every message is screened, and unclear ones go to agent review |
| Mode | Strict Guardrails (Always Debate) | **Strict protection**: every message goes to agent review |
| Mode | Chaos Mode (Bypass ML / Interception) | **No protection**: screening is skipped. Use it only for testing and comparison |
| Overview | Total Analyzed / Threats Neutralized / Authorized & Safe / Threat Block Rate | Messages checked / Blocked / Allowed / Block rate |
| Audit | Prompt / Query · Intervention Layer · ML Confidence · RLHF Feedback | Message · Stage · Risk score · Human review |
| Audit | Mark safe / Mark malicious | Mark as safe / Mark as harmful |
| Clearance | Security Clearance Passphrase / Save Clearance / Revoke | Admin access / Grant access / Revoke access |
| Chat | Type prompt or command for AI S.H.I.E.L.D. analysis... | Type a message to test the shield |
| Chat | `[SHUTDOWN PROTOCOL TRIGGERED]\n\nReason: …` | `Blocked during <stage>. <reason>` |
| Chat | System connection failed: … Please verify the API is running. | Cannot reach the server. Check that the API is running, then try again. |
| Console empty state | (blank) | Send a message to see how each check handles it. |

## Acceptance criteria

This spec covers slice 1 (foundation) of the redesign. The other slices are
separate specs, each accepted when its work starts: [0013 Trace model](../0013-web-trace-model/spec.md),
[0014 Audit view](../0014-web-audit-view/spec.md) and
[0015 Design-system hygiene](../0015-web-design-hygiene/spec.md). Slices 3 and 4
are behaviour-preserving refactors and need no spec. The design, copy and
status language above apply to all of them.

- **WEB-NAV-001**: Given the old routes `/dashboard`, `/dashboard/logs` and `/dashboard/settings`, when requested, then they redirect permanently to `/overview`, `/audit` and `/settings`.
- **WEB-CLEAR-001**: The browser never stores the passphrase. It is sent once to `POST /clearance` (spec 0012), and the client keeps only the returned `ClearanceStatus`. Every request goes out with `credentials: 'include'`, and any value under the legacy `localStorage` key `ai_shield_passphrase` is removed on load.
- **WEB-UI-004**: The app config sets `primary` and `neutral` so that primary renders as black in light mode and white in dark mode; `success`, `info` and `warning` map to the neutral scale; `error` stays red; and color mode is not forced (`preference` is `system`).

## Security & privacy considerations

- The passphrase no longer lives in the browser (WEB-CLEAR-001). Today it
  sits in plaintext in `localStorage`, where any script on the origin can read it.
  How the gateway keeps clearance is decided in spec 0012.
- The audit fix (WEB-AUDIT-002) stops the UI from misreporting enforcement
  decisions after a human review.
- No new data leaves the browser; all calls still go through `useShieldApi()`.

## Evaluation impact

None. No engine change.

## Decisions

Confirmed by the owner on 2026-09-24:

- **Colour:** strict monochrome. The only exception is `error` red on buttons
  for dangerous actions.
- **Routes:** `/dashboard/*` moves to `/overview`, `/audit` and `/settings`,
  with permanent redirects.
- **Copy:** plain, professional Malaysian English, as in the Copy table.
- **Passphrase:** server-side sessions in SQLite (spec 0012).
- **Pipeline status card:** deleted, and replaced with a static "How the
  checks work" section labelled as documentation. This is the default, and no
  objection was raised. A real health endpoint would be a separate API spec.

## Open questions

None. Passphrase storage is resolved: server-side sessions in SQLite, specified
in [spec 0012](../0012-clearance-sessions/spec.md), which must land first.
