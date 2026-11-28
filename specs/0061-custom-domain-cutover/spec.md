# 0061 — Custom domain cutover across web, api, admin, and landing

- **Status:** Implemented
- **Area:** API | WEB | DEV
- **Owner:** Terry Ong
- **Created:** 2026-11-28
- **Related:** [0041-same-origin-api-proxy](../0041-same-origin-api-proxy/spec.md), [0047-auth-flows-and-hardening](../0047-auth-flows-and-hardening/spec.md), [0049-stripe-pass-checkout](../0049-stripe-pass-checkout/spec.md), [0058-privacy-policy](../0058-privacy-policy/spec.md), [0059-admin-console-extraction](../0059-admin-console-extraction/spec.md), [0060-landing-site-and-legal](../0060-landing-site-and-legal/spec.md)

## Problem

`apps/web`, `apps/api`, `supabase/config.toml`, Stripe webhooks, and public crawler files (`robots.txt`, `sitemap.xml`, `llms.txt`) still reference temporary Vercel hostnames (`ai-shield-delta.vercel.app` and `ai-shield-backend.vercel.app`), and `apps/web` still hosts `/privacy` locally instead of linking to the canonical root domain `https://ai-shield.my`.

## Goals

- Cut over all four production hosts cleanly with zero downtime:
  - `https://ai-shield.my` (`apps/landing`, with `www.ai-shield.my` redirecting `308` to apex)
  - `https://play.ai-shield.my` (`apps/web`)
  - `https://admin.ai-shield.my` (`apps/admin`)
  - `https://api.ai-shield.my` (`apps/api`)
- Transition canonical legal links and `308` permanent redirects from `play.ai-shield.my` to `https://ai-shield.my`, superseding `WEB-PRIV-001` and `WEB-PRIV-002` from [Spec 0058](../0058-privacy-policy/spec.md).
- Strengthen registration and checkout consent on `play.ai-shield.my` (explicit unchecked opt-in consent checkbox on `/auth/register`, and explicit `USD` + immediate-activation + `/refund` disclosure on `/plans`).
- Roll out HSTS, CAA, and DMARC safely without locking out subdomains or breaking TLS renewals.

## Non-goals

- Implementing `apps/admin` ([Spec 0059](../0059-admin-console-extraction/spec.md)) or `apps/landing` ([Spec 0060](../0060-landing-site-and-legal/spec.md)).
- Changing gameplay mechanics, scoring, or database schemas.

## Behaviour

### 1. Game client (`apps/web` → `play.ai-shield.my`)

- Canonical URLs, Open Graph tags, JSON-LD, `robots.txt`, `sitemap.xml`, and `llms.txt` use `https://play.ai-shield.my` with zero remaining `ai-shield-delta.vercel.app` references.
- Legal links on `/auth/register`, `/plans`, and `/settings` point to `https://ai-shield.my/privacy` and `https://ai-shield.my/terms` (configured via public landing URL config); the game main menu (`/`) and `/auth/login` stay uncluttered while `ai-shield.my` hosts the site-wide legal footer.
- `/auth/register` requires an **explicit, unchecked opt-in consent checkbox** confirming agreement to the Terms of Service and acknowledgement of the Privacy Policy before account creation is submitted.
- `/plans` displays explicit `USD` currency, non-renewing 30-day pass terms, an immediate-activation notice (covering CPA 1999 / EU-UK digital delivery disclosure), and links to `https://ai-shield.my/privacy`, `/terms`, and `/refund`.
- Requests to `/privacy` and `/terms` on `play.ai-shield.my` return a **`308` Permanent Redirect** to `https://ai-shield.my/privacy` and `https://ai-shield.my/terms`.
- `apps/web/public/sitemap.xml` removes `/privacy` (now indexed on `ai-shield.my/sitemap.xml`), and `apps/web/public/.well-known/security.txt` lists `mailto:security@ai-shield.my`.

### 2. Supersession of Spec 0058 (`WEB-PRIV-001`, `WEB-PRIV-002`)

This spec formally supersedes `WEB-PRIV-001` and `WEB-PRIV-002` in [Spec 0058](../0058-privacy-policy/spec.md) because canonical privacy hosting moves from `apps/web` to `apps/landing` (`WEB-LAND-002`). `apps/web/test/privacy.test.ts` retains `WEB-PRIV-003` (data export download in `/settings`) and updates link/redirect assertions to `WEB-DOM-001` and `WEB-DOM-002`.

### 3. Gateway (`apps/api` → `api.ai-shield.my`) and external services

- `WEB_BASE_URL=https://play.ai-shield.my` drives auth confirmation (`/auth/confirmed`), password recovery (`/auth/reset-password`), and Stripe Checkout success/cancel URLs (`/plans`).
- `CORS_ORIGINS=https://play.ai-shield.my,https://admin.ai-shield.my`.
- Supabase Auth Site URL and Redirect URLs update to `https://play.ai-shield.my/auth/**` (retaining `ai-shield-delta.vercel.app/auth/**` for a 24-hour grace window so in-flight confirmation/recovery emails succeed, then removing it) and custom SMTP sends via Resend from `no-reply@ai-shield.my`.
- Legacy `ai-shield-delta.vercel.app` non-auth pages redirect immediately (`308`) to `https://play.ai-shield.my` at cutover so visitors never land on an outdated legal/privacy host or split session cookies across two origins; after the 24-hour email grace window, all paths on `ai-shield-delta.vercel.app` redirect `308` to `https://play.ai-shield.my`.
- Stripe webhook moves to `https://api.ai-shield.my/api/v1/billing/webhook` with zero-downtime secret rotation, and Stripe Business Profile URLs point to `https://ai-shield.my`.

## Acceptance criteria

- **WEB-DOM-001**: Given `NUXT_PUBLIC_SITE_URL=https://play.ai-shield.my` and `NUXT_PUBLIC_LANDING_URL=https://ai-shield.my`, when `apps/web` renders `/auth/register`, `/plans`, and `/settings`, then canonical tags use `https://play.ai-shield.my`, legal links point to `https://ai-shield.my/privacy` and `https://ai-shield.my/terms`, `/auth/register` enforces an explicit unchecked opt-in consent checkbox before submission, and `/plans` displays explicit `USD` pricing, immediate-activation terms, and a link to `https://ai-shield.my/refund`.
- **WEB-DOM-002**: Given a visitor requests `/privacy` or `/terms` on `apps/web`, then the server returns a `308` permanent redirect to `https://ai-shield.my/privacy` or `https://ai-shield.my/terms`.
- **WEB-DOM-003**: Given `apps/web/public/robots.txt`, `apps/web/public/sitemap.xml`, `apps/web/public/llms.txt`, and `apps/web/public/.well-known/security.txt`, then every game URL uses `https://play.ai-shield.my`, zero `ai-shield-delta.vercel.app` references remain, legal links point to `https://ai-shield.my`, and `security.txt` lists `mailto:security@ai-shield.my`.
- **API-DOM-001**: Given `APP_ENV=production` and `WEB_BASE_URL=https://play.ai-shield.my`, when auth confirmation, password recovery, or Stripe Checkout sessions are created, then all redirect, success, and cancel URLs target `https://play.ai-shield.my`.

## Security & privacy considerations

- **Accurate host-level cookie isolation:**
  - `shield_player_session` (`HttpOnly`, `SameSite=Lax`, `Secure`) and `shield_auth_browser` stay scoped strictly to `play.ai-shield.my` via the same-origin `/api/v1` proxy (never `.ai-shield.my`).
  - `shield_session` (`HttpOnly`, `SameSite=Strict`, `Secure`) stays scoped strictly to `admin.ai-shield.my` via its dedicated proxy.
  - `ai-shield.my` holds no session cookies.
- **Staged HSTS rollout:** Do not enable `includeSubDomains` with a 1-year `max-age` on day 0. Ramp `Strict-Transport-Security` from `max-age=300` → `max-age=86400` → `max-age=31536000; includeSubDomains` only after TLS is verified across `ai-shield.my`, `www`, `play`, `admin`, and `api`.
- **Vercel CAA safety:** DNS `CAA` records must authorize both `letsencrypt.org` and `pki.goog` (Google Trust Services, Vercel's fallback CA) so automated TLS renewals never fail.
- **DMARC rollout:** Start with `v=DMARC1; p=none; rua=mailto:security@ai-shield.my` while verifying SPF/DKIM alignment on `no-reply@` and `support@ai-shield.my`, then tighten to `p=quarantine` and `p=reject`.

## Evaluation impact

None. No change to `packages/engine`.

## Open questions

None. (Resolved: immediate `308` redirect on non-auth routes of `ai-shield-delta.vercel.app` to preserve SEO and legal/cookie consistency, with a 24-hour Supabase Redirect URL grace window for in-flight `/auth/**` emails before full cutover.)

## Verification

### 2026-11-28 · commit ea6bf79 (+ uncommitted changes)

- Criteria: WEB-DOM-001, WEB-DOM-002, WEB-DOM-003, API-DOM-001
- Red: 4 failing test(s) before implementation (`Custom domain cutover (spec 0061) [WEB-DOM-001] links to ai-shield.my legal pages, requires register consent checkbox, and discloses USD + refund on /plans`, `Custom domain cutover (spec 0061) [WEB-DOM-002] returns 308 permanent redirects from /privacy and /terms to ai-shield.my`, `Custom domain cutover (spec 0061) [WEB-DOM-003] updates robots.txt, sitemap.xml, llms.txt to play.ai-shield.my and adds security.txt`)
- Green: 4 passing test(s)
- Gate: `mise run check` passed