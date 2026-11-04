# 0011 — Web product redesign: tasks

Run as six SDD cycles, one per slice (see [plan.md](plan.md#delivery-six-slices-one-sdd-cycle-each)).
`mise run sdd:done` ticks the criterion lines automatically.

## Slice 1: Foundation

- [x] Spec 0012 is `Implemented` (WEB-CLEAR-001 needs `/clearance`)
- [ ] `mise run sdd:start 0011 WEB-UI-004 WEB-NAV-001 WEB-CLEAR-001`
- [ ] **WEB-UI-004**: write failing test
- [ ] **WEB-NAV-001**: write failing test
- [ ] **WEB-CLEAR-001**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Theme tokens + fonts + component defaults; one shell; routes + redirects; `ClearanceModal`; `error.vue`; head + favicon
- [ ] `mise run sdd:green`, `mise run sdd:verify`, `mise run sdd:done`

## Slices 2–6

- Slice 2: [spec 0013](../0013-web-trace-model/tasks.md)
- Slice 3: `mise run sdd:start --refactor "0011 slice 3: generic PipelineNode driven by derivePipelineGraph"`
- Slice 4: `mise run sdd:start --refactor "0011 slice 4: console composable, empty state, verdict row"`
- Slice 5: [spec 0014](../0014-web-audit-view/tasks.md), plus the Overview and Settings pages
- Slice 6: [spec 0015](../0015-web-design-hygiene/tasks.md)
