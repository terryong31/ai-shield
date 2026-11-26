# 0050 — Campaign redesign: tasks

Run as four SDD cycles, one per slice of the plan. `mise run sdd:done` ticks the criterion lines automatically.

## Slice 1: score

- [ ] `mise run sdd:start 0050 ENG-FAIR-001 ENG-FAIR-002 ENG-FAIR-003 ENG-FAIR-004 ENG-FAIR-005 ENG-FAIR-006 ENG-FAIR-007 ENG-FAIR-008`
- [ ] **ENG-FAIR-001** to **ENG-FAIR-008**: write failing tests; update the tests of the replaced criteria
- [ ] `sdd:red`, implement, `sdd:green`, `sdd:verify`, `sdd:done`

## Slice 2: limits and board size

- [x] **ENG-FAIR-009**, **ENG-FAIR-010**, **ENG-FAIR-011**

## Slice 3: gateway

- [x] **API-FAIR-001** to **API-FAIR-008**
- [ ] `mise run contract`; migration for version 4 scores

## Slice 4: web

- [x] **WEB-FAIR-001** to **WEB-FAIR-004**
- [ ] Screenshot the game bar and the result modals

## Close

- [ ] Update `docs/reference/` and `CHANGELOG.md`
- [ ] Mark each replaced criterion `Replaced by <new ID> (0050).`
