# 0061 — Custom domain cutover across web, api, admin, and landing: tasks

- [ ] Complete Spec 0059 and Spec 0060
- [ ] Have a human mark `spec.md` `Accepted` (and update `specs/README.md`)
- [ ] `mise run sdd:start 0061`
- [x] **WEB-DOM-001**: write failing test for `play.ai-shield.my` canonical URLs, `ai-shield.my` legal links, `/auth/register` opt-in consent checkbox, and `/plans` USD + `/refund` disclosure
- [x] **WEB-DOM-002**: write failing test for `308` permanent redirects from `/privacy` and `/terms` on `apps/web`
- [x] **WEB-DOM-003**: write failing test verifying `robots.txt`, `sitemap.xml`, `llms.txt`, and `security.txt`
- [x] **API-DOM-001**: write failing test verifying `WEB_BASE_URL=https://play.ai-shield.my` propagates to auth and Stripe URLs
- [ ] `mise run sdd:red` accepted
- [ ] Implement `apps/web` and `supabase/config.toml` changes (and mark `WEB-PRIV-001`/`002` superseded in Spec 0058 notes); `mise run sdd:green` accepted
- [ ] Execute DNS (including dual CAA `letsencrypt.org` + `pki.goog` and initial DMARC `p=none`), Infisical/Vercel env vars, Supabase Auth, and Stripe webhook cutover
- [ ] Ramp HSTS (`300` → `86400` → `31536000; includeSubDomains`) and DMARC (`p=none` → `p=quarantine` → `p=reject`) after verification
- [ ] Update `docs/reference/configuration.md` and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
