# 0060 — Standalone landing site, bilingual legal pages, and client changelog: plan

## 1. Scaffold `apps/landing` from `nuxt-ui-templates/saas`
Prerequisite: [Spec 0059](../0059-admin-console-extraction/spec.md) (`apps/*` workspace, SDD multi-app support, and CI wiring).

```bash
bun create nuxt@latest apps/landing -- -t ui/saas
bun install
```

Strip unused template routes (`login.vue`, `signup.vue`, `layouts/auth.vue`, unused `blog/` and `docs/` demos).

## 2. Wire `apps/landing` into monorepo, CI, and Vercel
- **`scripts/affected.sh` & `scripts/vercel_ignore.sh`:** Add `deploy-landing` target watching `apps/landing/**` and root workspace files; support `landing` in `vercel_ignore.sh`.
- **`mise.toml` & `.github/workflows/ci.yml`:** Add `landing:dev` (port `3001`), `test:landing`, `lint:landing`, `typecheck:landing`, `a11y:landing` (`@axe-core/playwright`), and wire them into `mise run check` and CI.
- **Vercel project:** Create a Vercel project with Root Directory `apps/landing` and Ignored Build Step `bash ../../scripts/vercel_ignore.sh landing`.

## 3. Configure `@nuxtjs/i18n`, Nuxt Content, and static prerendering
- Install `@nuxtjs/i18n` with `strategy: 'prefix_except_default'`, `defaultLocale: 'en'`, `baseUrl: 'https://ai-shield.my'`, locales `en` (`en-MY`) and `ms` (`ms-MY`), and locale files `apps/landing/i18n/locales/en.json` and `ms.json`.
- Store client-facing release notes in `apps/landing/content/changelog/*.md` (frontmatter: `title`, `description`, `date`, `version`, `badge`) and render with Nuxt UI `UChangelogVersions` / `UChangelogVersion`.
- Prerender all routes (`/` , `/changelog`, `/privacy`, `/terms`, `/refund`, `/ms`, `/ms/changelog`, `/ms/privacy`, `/ms/terms`, `/ms/refund`, `/sitemap.xml`) via `nitro.prerender` and `routeRules`.
- Add `apps/landing/public/.well-known/security.txt`, `robots.txt`, `sitemap.xml`, `llms.txt`, and accessible `app/error.vue`.

## 4. Telemetry & security headers (`apps/landing/nuxt.config.ts`)
- Enable `@vercel/analytics` and `@vercel/speed-insights` via a client plugin matching `apps/web/app/plugins/analytics.client.ts`.
- Apply baseline headers on `/**` (`Content-Security-Policy` permitting Vercel Analytics/Speed Insights on `'self'` in production and `va.vercel-scripts.com` in dev, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`). HSTS is managed safely during domain cutover in [Spec 0061](../0061-custom-domain-cutover/spec.md) so `includeSubDomains` is only enabled after all subdomains verify TLS.

## 5. Automated WCAG 2.2 AA verification (`WEB-ACCESS-001`)
Add a Playwright + `@axe-core/playwright` test script in `apps/landing/test/a11y.spec.ts` that boots the built static preview and asserts zero `critical` or `serious` WCAG 2.2 AA violations on `/`, `/changelog`, `/privacy`, `/terms`, and `/refund`.
