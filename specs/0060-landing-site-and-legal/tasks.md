# 0060 — Standalone landing site, bilingual legal pages, and client changelog: tasks

- [ ] Complete Spec 0059 (`apps/*` multi-app SDD & CI support)
- [ ] Have a human mark `spec.md` `Accepted` (and update `specs/README.md`)
- [ ] `mise run sdd:start 0060`
- [x] **WEB-LAND-001**: write failing test for security headers, canonical/`hreflang`/OG metadata, and semantic landmarks
- [x] **WEB-LAND-002**: write failing test for `/privacy` and `/ms/privacy` (Spec 0058 tables + BYOK + SMTP + 72h PDPC breach notice + locale switcher)
- [x] **WEB-LAND-003**: write failing test for `/terms`, `/refund` (CPA 1999 + 3-day SLA), and `/.well-known/security.txt`
- [x] **WEB-LAND-004**: write failing test for `/changelog` reverse-chronological feed
- [x] **WEB-ACCESS-001**: write failing `@axe-core/playwright` WCAG 2.2 AA check across all landing routes
- [ ] `mise run sdd:red` accepted
- [ ] Scaffold `apps/landing` from `nuxt-ui-templates/saas`, configure `@nuxtjs/i18n`, Nuxt Content changelog, legal pages, `security.txt`, and CI/Vercel wiring; `mise run sdd:green` accepted
- [ ] Update `docs/reference/repository-layout.md` and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
