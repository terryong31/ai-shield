# 0041 — Same-origin API proxy: tasks

Run as one SDD cycle. `mise run sdd:done` ticks the criterion lines automatically.

- [x] `mise run sdd:start 0041`
- [x] **WEB-PROXY-001**: write failing test
- [x] **WEB-PROXY-002**: write failing test
- [x] **WEB-PROXY-003**: write failing test
- [x] **WEB-PROXY-004**: write failing test
- [x] **WEB-PROXY-005**: write failing test
- [x] **WEB-PROXY-006**: write failing test
- [x] **WEB-PROXY-007**: write failing test
- [x] **WEB-PROXY-008**: write failing test
- [x] **WEB-PROXY-009**: write failing test
- [x] **WEB-PROXY-010**: write failing test
- [x] **WEB-PROXY-011**: write failing test
- [x] **WEB-PROXY-012**: write failing test
- [x] **WEB-PROXY-013**: write failing test
- [x] **WEB-PROXY-014**: write failing test
- [x] **WEB-PROXY-015**: write failing test
- [x] `mise run sdd:red` accepted
- [x] Implement; `mise run sdd:green` accepted
- [x] Config: `nuxt.config.ts` (private `apiProxyTarget`, comment), `apps/web/Dockerfile`, `compose.yaml`
- [x] Docs: `docs/reference/configuration.md`, `docs/how-to/deploy.md` (incl. Vercel checklist, obsolete CORS note), `docs/reference/repository-layout.md`, note on ADR 0004
- [x] `CHANGELOG.md` (incl. `PUBLIC_API_URL` → `NUXT_API_PROXY_TARGET` migration note)
- [x] Manual check: `mise run dev`, sign in, leaderboard live stream
- [x] `mise run sdd:verify`, then `mise run sdd:done`
