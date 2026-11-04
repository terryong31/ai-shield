# 0011 — Web product redesign: implementation plan

- **Spec:** [spec.md](spec.md)

## Design direction: "instrument"

The shield is a measuring instrument for prompts, so the UI borrows from lab
equipment and technical drawings rather than sci-fi dashboards: hairlines,
dot grids, tabular numbers, mono data labels, and no glow, gradients, blur or
hue. Monochrome forces hierarchy to come from type, weight, spacing and
contrast.

| Token | Value | Why |
| --- | --- | --- |
| `primary` | black (light) / white (dark), via `--ui-primary` in `main.css` | Monochrome actions; the highest contrast is reserved for the primary action and `blocked` |
| `neutral` | `neutral` (pure grey) | `zinc` has a blue cast that reads as default Tailwind |
| `success` / `info` / `warning` | mapped to the neutral scale | Nothing on screen relies on hue |
| `error` | red, **only** on `UButton`s for dangerous actions (WEB-UI-005) | A red button always means "this removes protection, removes access or discards data" |
| `--ui-radius` | `0.25rem` | Tighter corners than the soft defaults |
| Sans | Geist | Neutral grotesk, strong at small sizes |
| Mono | Geist Mono, `tabular-nums` | Scores, IDs, timings and labels line up |
| Labels | 11px mono, uppercase, `tracking-wide`, `text-muted` | Used only for data labels, never for headings |
| Canvas | Vue Flow `Background` dots in `--ui-border` | Graph paper, not a "cyber" grid |
| Motion | 150ms ease-out; animated dashed edges for `active`; everything disabled under `prefers-reduced-motion` | Motion means "work in progress", nothing more |

Fonts load through `@nuxt/fonts`, which Nuxt UI v4 already registers, so no
new dependency is needed. Component defaults (button `color: neutral`, badge
`variant: outline`, card `variant: outline`) go in `app.config.ts`, so pages
do not repeat props.

**Signature element:** the trace. Each node shows a mono label (`01 MESSAGE`,
`02 SCREENING` …), its status glyph and one datum (a score, categories, the
number of debate turns, a policy). Selecting a node opens the inspector with
that layer's full output. The same data is shown as a vertical `UTimeline`
with millisecond offsets in the Timeline tab.

## Target structure

```
app/
  app.vue                         UApp + NuxtLoadingIndicator + NuxtLayout + ClearanceModal
  app.config.ts                   monochrome theme + component defaults
  error.vue                       UError
  assets/css/main.css             tokens, fonts, Vue Flow theming (no !important)
  layouts/default.vue             single UDashboardGroup shell
  components/
    AppSidebar.vue                nav, clearance status, UColorModeButton
    ClearanceModal.vue            UModal + UForm (moved out of app.vue)
    console/
      ConsoleChat.vue             UChatMessages + UChatPrompt, mode and clearance in the prompt footer
      ConsoleEmptyState.vue       UEmpty + sample prompts (benign, injection, tool abuse)
      MessageVerdict.vue          one-line verdict row under an assistant message
      TracePanel.vue              UTabs: Graph | Timeline, plus the inspector
      TraceTimeline.vue           UTimeline over workflow.timeline
      TraceInspector.vue          details of the selected node (debate transcript, categories…)
    pipeline/
      PipelineCanvas.vue          VueFlow host; nodes and edges from derivePipelineGraph
      PipelineNode.vue            the one generic node (replaces 7 components + NodeContainer)
    audit/
      AuditTable.vue              UTable with filters, pagination, row select
      AuditRecordSlideover.vue    USlideover: message, reason, stage, risk, moderation categories, debate transcript (metadata.agentDialogue), review
    overview/
      StatTiles.vue               4 figures, no coloured icon bubbles
      PipelineExplainer.vue       static and labelled as documentation
  composables/
    useShieldApi.ts               unchanged
    useConsole.ts                 chat + trace state (moved out of ChatInterface.vue)
    useClearance.ts               replaces usePassphrase.ts
    useSecurityMode.ts            unchanged API
  utils/
    chatStream.ts                 + moderation, debate[], timeline, block copy
    pipelineGraph.ts              derivePipelineGraph, statusAppearance, PIPELINE_NODES
    audit.ts                      filterAuditRecords, applyReview
    format.ts                     formatConfidence, formatOffset, relative time
  pages/
    index.vue  overview.vue  audit.vue  settings.vue
```

Deleted: `layouts/dashboard.vue`, `components/workflow/*`,
`components/dashboard/*`, `pages/dashboard/*`, `composables/usePassphrase.ts`,
`composables/useShieldWorkflow.ts` (folded into `useConsole`).

## Current → target component map

| Where | Today | Target |
| --- | --- | --- |
| Top header (`layouts/default.vue`) | hand-built `<header>` + tooltip buttons | `UDashboardSidebar` + `UNavigationMenu` (shared shell) |
| Workspace split (`pages/index.vue`) | `USplitter` with custom handle markup | `UDashboardPanel` ×2 (`resizable`), one for chat and one for the trace |
| Nodes | 7 components, raw colours, `<span>` chips | `PipelineNode` using `UBadge`, `UIcon`, semantic tokens, and a status class from `statusAppearance` |
| Node detail | none | `TraceInspector` in the trace panel (`UCard`, `UAccordion` for the transcript) |
| Timeline | none | `UTimeline` |
| Chat badges | 4 coloured `UBadge`s | one `MessageVerdict` line: `RISK 91% · AGENT REVIEW · LIMITED TOOLS`, mono, `UBadge variant="outline"` |
| Blocked message | red ring and red text | inverted block with a `shield-x` icon |
| Empty console | blank | `UEmpty` + suggestion `UButton`s |
| Stats | `UPageCard` with coloured round icons | `UPageCard variant="outline"`, large mono figures, no icons |
| Pipeline status | fake `ACTIVE/READY/STANDBY` | `PipelineExplainer` (static, labelled) |
| Audit table | fixed 30 rows, no detail | `UTable` + `UTabs` (All / Blocked / Allowed / Unreviewed) + `UInput` search + `UPagination` + `USlideover` |
| Review buttons | green "Mark safe" / red "Mark malicious" | `UFieldGroup` of two outline buttons with keyboard shortcuts `S` / `M` in the slideover |
| Settings mode | `USelect` + toast on every change | `URadioGroup variant="card"` with a description per mode |
| Clearance | modal in `app.vue`, passphrase in `localStorage` | "Admin access" `ClearanceModal` using `UForm`; the browser keeps only the status returned by the gateway (spec 0012); sidebar footer shows the state with `UChip`; Revoke is `color="error"` |
| Theme | forced dark | `UColorModeButton` in the sidebar; `preference: 'system'` |
| Shortcuts | none | `defineShortcuts`: `g c`, `g o`, `g a`, `g s`, `/` focuses the prompt, `meta_k` opens a `UDashboardSearch` palette |
| Head | none | `useSeoMeta` per page, title template `%s · S.H.I.E.L.D.`, SVG favicon mark |

## Interfaces

```ts
// utils/pipelineGraph.ts
export type NodeStatus = 'idle' | 'active' | 'passed' | 'flagged' | 'blocked' | 'skipped'
export type PipelineNodeId = 'input' | 'classifier' | 'moderation' | 'router' | 'adjudication' | 'assistant' | 'tools' | 'blocked'
export interface PipelineNodeView { id: PipelineNodeId, status: NodeStatus, datum?: string }
export interface PipelineGraph { nodes: PipelineNodeView[], activeEdges: string[], traversedEdges: string[] }
export function derivePipelineGraph(state: WorkflowState): PipelineGraph
export function statusAppearance(status: NodeStatus): { icon: string, label: string, class: string }

// types/workflow.ts (additions)
interface WorkflowState {
  moderation: { safe: boolean, categories: string[] } | null
  debate: { agent: 'ANALYST' | 'WARDEN', message: string }[]
  timeline: { type: ChatEvent["type"], at: number | null, summary: string }[]
  blockedLayer?: DecisionLayer
}

// utils/chatStream.ts (additive; existing calls keep working)
interface ChatTurn { workflow: WorkflowState, metadata: ShieldMetadata, text: string, startedAt?: number }
export function applyChatEvent(turn: ChatTurn, event: ChatEvent, now?: number): ChatTurn
export const STAGE_LABEL: Record<DecisionLayer, string>   // screening | agent review | system check
export const shutdownNotice = (reason: string, layer?: DecisionLayer) => string   // "Blocked during <stage>. <reason>"


// utils/audit.ts
export interface AuditFilter { action: 'all' | 'ALLOWED' | 'BLOCKED', review: 'all' | 'reviewed' | 'unreviewed', text: string }
export function filterAuditRecords(records: AuditRecord[], filter: AuditFilter): AuditRecord[]
export function applyReview(record: AuditRecord, label: 0 | 1): AuditRecord

// composables/useClearance.ts (state is ClearanceStatus from spec 0012; never the passphrase)
export function useClearance(): { status: Ref<ClearanceStatus>, refresh(): Promise<void>, grant(passphrase: string): Promise<void>, revoke(): Promise<void> }
// utils/clearance.ts
export function dropLegacyPassphrase(local: Storage): void   // removes `ai_shield_passphrase`
```

All of these changes are additive, so spec 0008's tests pass unchanged
(WEB-TRACE-007). `lastAgentMessage` stays on `WorkflowState` and is used as the
adjudication node's preview; `debate` feeds the inspector's transcript.
`shutdownNotice` keeps its name, and WEB-STREAM-004 compares against the
helper, so changing its text does not break that test.

## Delivery: six slices, one SDD cycle each

Each slice is mergeable on its own, and the app works after every slice.

| # | Slice | Cycle | Criteria |
| --- | --- | --- | --- |
| 1 | **Foundation**: theme tokens, fonts, `app.config` defaults, `main.css` cleanup, single shell + sidebar, new routes + redirects, `ClearanceModal`, `error.vue`, head/favicon, color mode | spec | WEB-UI-004, WEB-NAV-001, WEB-CLEAR-001 |
| 2 (spec 0013) | **Trace model**: extend `chatStream.ts`, add `pipelineGraph.ts` (logic only, no UI yet) | spec | WEB-TRACE-001 … 007 |
| 3 | **Pipeline canvas**: `PipelineNode`, `PipelineCanvas`, inspector, timeline tab; delete `components/workflow/*` | refactor (the behaviour is covered by slice 2) | none |
| 4 | **Console**: `useConsole`, `ConsoleChat`, empty state, verdict row, shortcuts | refactor | none |
| 5 (spec 0014) | **Audit, Overview and Settings**: `audit.ts`, `format.ts`, table, slideover, filters, pagination; stat tiles; explainer; radio-card settings | spec | WEB-AUDIT-001 … 003 |
| 6 (spec 0015) | **Hygiene gate**: source-scan tests, a11y pass (focus rings, `aria-label`s, contrast in both themes), docs, CHANGELOG, new screenshot | spec | WEB-UI-001 … 003, WEB-UI-005 |

The source scans run last on purpose: they fail against today's code, and
they pass only once slices 3–5 have removed the old components.

## Boundaries check

- [x] `packages/engine` untouched
- [x] `apps/web` still talks to the backend only through `useShieldApi()` and the generated contract; no contract change
- [x] No new configuration (no runtime config added)
- [x] No new dependency: `@nuxt/fonts` and `@nuxtjs/color-mode` ship with `@nuxt/ui` v4

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep seven node components and just restyle them | Duplication stays; status logic stays in a `watch` inside a component, untested |
| A third-party graph layout (dagre, elk) | New dependency; eight fixed nodes do not need auto-layout |
| A monochrome accent in a single hue (for example blue) | Not monochrome, and it pulls the design back towards default Nuxt UI |
| Keep the dark-only theme | A monochrome system is cheap to support in both modes, and light mode suits screenshots and papers |

## Risks and rollback

- **Status legibility without colour.** Mitigation: the status table pairs
  every status with an icon and a text label (WEB-TRACE-005). Check in both
  themes with a greyscale screenshot.
- **Vue Flow theming.** Its default stylesheet fights semantic tokens today
  (hence the `!important`s). Mitigation: drop `theme-default.css` and style
  nodes and edges from `main.css` with `--ui-*` variables.
- **Bookmarked routes.** Covered by the permanent redirects (WEB-NAV-001).
- **Rollback.** Each slice is its own PR; revert the slice.
