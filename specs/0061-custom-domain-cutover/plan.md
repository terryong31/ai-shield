# 0061 — Custom domain cutover across web, api, admin, and landing: plan

Prerequisites: [Spec 0059](../0059-admin-console-extraction/spec.md) and [Spec 0060](../0060-landing-site-and-legal/spec.md) implemented and deployed.

## 1. Code changes (`apps/web`, `supabase/config.toml`)
- Add `landingUrl: 'https://ai-shield.my'` to `runtimeConfig.public` in `apps/web/nuxt.config.ts` (overridable via `NUXT_PUBLIC_LANDING_URL`).
- Add `308` redirects in `apps/web/nuxt.config.ts` `routeRules`:
  - `'/privacy': { redirect: { to: 'https://ai-shield.my/privacy', statusCode: 308 } }`
  - `'/terms': { redirect: { to: 'https://ai-shield.my/terms', statusCode: 308 } }`
- Remove `apps/web/app/pages/privacy.vue` and `/privacy` from `INDEXABLE_PATHS` in `apps/web/app/app.vue`.
- Update legal links in `index.vue`, `auth/login.vue`, `auth/register.vue`, `plans.vue`, and `settings.vue` to use `${landingUrl}/privacy`, `/terms`, and `/refund`.
- Add explicit unchecked opt-in consent checkbox on `apps/web/app/pages/auth/register.vue` (disabling submit or showing validation error until checked).
- Add explicit `USD` + immediate-activation notice + `/refund` link on `apps/web/app/pages/plans.vue`.
- Update `apps/web/public/robots.txt`, `sitemap.xml`, `llms.txt`, add `apps/web/public/.well-known/security.txt`, and update `apps/web/test/seo.test.ts` and `apps/web/test/privacy.test.ts`.
- Update `supabase/config.toml` `site_url` and `additional_redirect_urls` to `https://play.ai-shield.my`.

## 2. Vercel domain attachment & Namecheap DNS setup
1. Verify Vercel CLI auth (`vercel whoami`) and attach each domain to its Vercel project:
   - `vercel domains add ai-shield.my <landing-project>` and `vercel domains add www.ai-shield.my <landing-project>` (configure `www.ai-shield.my` as a `308` redirect to `https://ai-shield.my` in Vercel Project Settings → Domains).
   - `vercel domains add play.ai-shield.my <web-project>`
   - `vercel domains add admin.ai-shield.my <admin-project>`
   - `vercel domains add api.ai-shield.my <api-project>`
2. Run `vercel domains verify <domain> --project <project> --json` (or inspect Project Settings → Domains) to obtain the **exact** DNS records (`A` / `CNAME` targets and any ownership-verification `TXT` records) assigned by Vercel for each host. Do not hardcode universal IPs or CNAME targets.
3. Configure the exact Vercel-returned DNS records in **Namecheap** (authoritative DNS for `ai-shield.my`), preserving unrelated records.
4. Add `CAA` records in Namecheap authorizing **both** `0 issue "letsencrypt.org"` and `0 issue "pki.goog"` (Google Trust Services, Vercel's fallback CA).
5. Add **Resend** DNS verification records (`DKIM`, `SPF`, and `MX` if receiving/routing) for `ai-shield.my`, plus initial DMARC `v=DMARC1; p=none; rua=mailto:security@ai-shield.my`.
6. Rerun `vercel domains verify` for all five hostnames (`ai-shield.my`, `www`, `play`, `admin`, `api`) and confirm DNS propagation and valid TLS certificates before ramping HSTS.

## 3. Environment variables (Infisical + Vercel)
- **`apps/api` (`/api` prod):** `WEB_BASE_URL=https://play.ai-shield.my`, `CORS_ORIGINS=https://play.ai-shield.my,https://admin.ai-shield.my`.
- **`apps/web` (`/web` prod):** `NUXT_PUBLIC_SITE_URL=https://play.ai-shield.my`, `NUXT_API_PROXY_TARGET=https://api.ai-shield.my`, `NUXT_PUBLIC_LANDING_URL=https://ai-shield.my`, `NUXT_PUBLIC_PRIVACY_CONTACT_EMAIL=support@ai-shield.my`.
- **`apps/admin` (`/admin` prod):** `NUXT_PUBLIC_SITE_URL=https://admin.ai-shield.my`, `NUXT_API_PROXY_TARGET=https://api.ai-shield.my`, `NUXT_API_ADMIN_PROXY_SECRET=<secret>`.

## 4. Zero-downtime service cutover
1. **Supabase Auth:** Add `https://play.ai-shield.my/auth/**` to Redirect URLs (keep `ai-shield-delta.vercel.app` for 24h), set Site URL to `https://play.ai-shield.my`, enable custom SMTP sender `no-reply@ai-shield.my`.
2. **Stripe Webhook:** Create endpoint `https://api.ai-shield.my/api/v1/billing/webhook`, rotate `STRIPE_WEBHOOK_SECRET` in Infisical/Vercel, redeploy `apps/api`, verify test event delivery, disable old webhook. Update Stripe Business Profile URLs to `https://ai-shield.my`.
3. **Staged HSTS & DMARC hardening:**
   - Start HSTS at `max-age=300` on all hosts → after 24h clean TLS verification, raise to `max-age=86400` → after 7 days, set `max-age=31536000; includeSubDomains`.
   - After verifying SPF/DKIM pass in DMARC reports, move DMARC from `p=none` → `p=quarantine` → `p=reject`.
4. **Post-cutover cleanup (after 24h):** Remove `ai-shield-delta.vercel.app` from Supabase Redirect URLs; submit `ai-shield.my/sitemap.xml` and `play.ai-shield.my/sitemap.xml` to Google Search Console; verify with `securityheaders.com`, SSL Labs, Lighthouse, and W3C Nu HTML Checker.
