# 0053 — Frontend security hardening: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0053`
- [x] **WEB-SEC-001**: write failing test for global HTTP security headers and production HSTS
- [x] **WEB-SEC-002**: write failing test for `Cache-Control: no-store` on `/_console`, `/settings`, and `/plans`
- [x] **WEB-SEC-003**: write failing test for auth URL `error_description` rejection and `error_code` allowlist
- [x] **WEB-SEC-004**: write failing test for analytics query-string scrubbing on `/auth/**`
- [x] **WEB-SEC-005**: write failing test for Nitro proxy 2 MiB body limit returning `413`
- [x] **WEB-SEC-006**: write failing test for Nitro proxy rejecting `same-site` and headerless production mutations with `403`
- [x] **WEB-SEC-007**: write failing test for `/_console` Clear scoreboard confirmation modal (`CLEAR`)
- [x] **WEB-SEC-008**: write failing test verifying `/_console` skips `getScores` until admin clearance is granted
- [x] **WEB-SEC-009**: write failing test for `isAllowedCheckoutUrl` blocking non-Stripe or non-HTTPS redirect targets
- [x] **WEB-SEC-010**: write failing test for `serializeJsonLd` escaping `<` as `\u003c`
- [x] **WEB-SEC-011**: write failing test verifying `public/robots.txt` does not list `/_console`
- [x] **WEB-SEC-012**: write failing test for Change Email Zod schema and no `"latest"` in `apps/web/package.json`
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
