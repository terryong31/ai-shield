# 0026 — Game-only cleanup: tasks

- [x] `mise run sdd:start 0026`
- [x] **API-CLEAN-001** Removed routes return `404`; contract lists only kept paths
- [x] **API-CLEAN-002** No legacy component schemas in the contract
- [x] **API-CLEAN-003** Kept game/auth/clearance/health tests pass unchanged
- [x] **API-CLEAN-004** No `audit.requests`; drop migration
- [x] **ENG-CLEAN-001** Engine public API is game-only; `wrap_untrusted` kept
- [x] **ENG-CLEAN-002** No imports of removed modules; engine purity kept
- [x] **WEB-CLEAN-001** Legacy web files and API methods gone
- [x] **WEB-CLEAN-002** Game-only admin console
- [x] **REPO-CLEAN-001** No `eval` task; specs superseded or retired; `mise run check` passes
- [x] `mise run sdd:red` accepted
- [x] Delete legacy code and tests; `mise run sdd:green` accepted
- [x] Migration via `mise run db:migration drop_audit_requests`
- [x] `mise run contract`
- [x] Update `AGENTS.md`, `README.md`, `docs/`, `MODEL_CARD.md`, `CHANGELOG.md`
- [x] Mark superseded specs and retire removed criteria
- [x] `mise run sdd:verify`, then `mise run sdd:done`
