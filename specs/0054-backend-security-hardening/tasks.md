# 0054 — Backend security hardening: tasks

Run as one SDD cycle (or several, one per slice of IDs). `mise run sdd:done`
ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0054 [IDs…]`
- [x] **API-SEC-001**: write failing test
- [x] **API-SEC-002**: write failing test
- [x] **API-SEC-003**: write failing test
- [x] **API-SEC-004**: write failing test
- [x] **API-SEC-005**: write failing test
- [x] **API-SEC-006**: write failing test
- [x] **API-SEC-007**: write failing test
- [x] **API-SEC-008**: write failing test
- [x] **API-SEC-009**: write failing test
- [x] **API-SEC-010**: write failing test
- [x] **API-SEC-011**: write failing test
- [x] **API-SEC-012**: write failing test
- [x] **API-SEC-013**: write failing test
- [x] **API-SEC-014**: write failing test
- [x] **ENG-SEC-001**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement; `mise run sdd:green` accepted
- [ ] Update reference docs (`docs/reference/configuration.md`) and `CHANGELOG.md`
- [ ] Regenerate the API contract (`mise run contract`)
- [ ] `mise run sdd:verify`, then `mise run sdd:done`

## Operational checklist (post-merge / dashboard)

- [ ] Supabase Dashboard: enable **Leaked Password Protection** and **Enforce SSL**
- [ ] Vercel (`ai-shield`): switch **Bot Protection** from `Log` to `Challenge`
- [ ] Vercel (`ai-shield-backend`): add Firewall custom rule blocking direct traffic without `x-shield-proxy-secret` (except `/api/v1/health` and `/api/v1/billing/webhook`)
- [ ] Vercel (`ai-shield-backend`): remove unused `STRIPE_API_KEY` env var from Production
