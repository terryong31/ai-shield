# 0060 — Standalone landing site, bilingual legal pages, and client changelog

- **Status:** Implemented
- **Area:** WEB | DEV
- **Owner:** Terry Ong
- **Created:** 2026-11-28
- **Related:** [0053-frontend-security-hardening](../0053-frontend-security-hardening/spec.md), [0058-privacy-policy](../0058-privacy-policy/spec.md), [0059-admin-console-extraction](../0059-admin-console-extraction/spec.md), [0061-custom-domain-cutover](../0061-custom-domain-cutover/spec.md)

## Problem

`ai-shield` has no root-domain marketing site, no Terms of Service, no standalone Refund Policy required for Stripe merchant review, no Bahasa Malaysia privacy notice required under Malaysia's Personal Data Protection Act (PDPA 2010 + 2024 Amendment), and no client-facing product changelog.

## Goals

- Build an independently deployable marketing and legal site in `apps/landing` for `https://ai-shield.my` (in both English and Bahasa Malaysia).
- Host the canonical Privacy Policy (`/privacy`), Terms of Service (`/terms`), standalone Refund Policy (`/refund`), client-facing Changelog (`/changelog`), and RFC 9116 `/.well-known/security.txt`.
- Meet web SaaS standards: semantic HTML5, WCAG 2.2 AA (verified by an automated accessibility harness), Core Web Vitals, strict security headers, SEO (`canonical`, `hreflang`, `sitemap.xml`, `robots.txt`, `llms.txt`, JSON-LD), Stripe merchant rules, and Malaysia PDPA 2010 + 2024 Amendment.
- Explicitly prepare `apps/landing` to supersede `WEB-PRIV-001` and `WEB-PRIV-002` from [Spec 0058](../0058-privacy-policy/spec.md) when [Spec 0061](../0061-custom-domain-cutover/spec.md) cuts over `play.ai-shield.my`.

## Non-goals

- Running gameplay, authentication, or Stripe Checkout on `ai-shield.my` (all interactive player flows stay on `https://play.ai-shield.my`).
- Adding third-party advertising trackers or a cookie-consent banner (none are loaded; if third-party tracking is added later, an explicit opt-in banner is mandatory).
- Performing DNS, Supabase Auth, Stripe webhook, or `apps/web` domain cutover (covered in [Spec 0061](../0061-custom-domain-cutover/spec.md)).
- Providing formal legal advice (legal copy is an engineering compliance draft for review before commercial launch).

## Behaviour

### 1. Public routes and bilingual coverage (`en` at `/...`, `ms` at `/ms/...`)

| Route | Purpose | Required content |
| --- | --- | --- |
| `/` (and `/ms`) | Product landing page | Hero with primary CTA to `https://play.ai-shield.my`, visual board preview, 19-level campaign overview, defence tools showcase, public pricing (`Free $0` vs `30-Day Pass $5 USD`, one-time non-renewing payment), FAQ, footer linking `/changelog`, `/privacy`, `/terms`, `/refund`, `support@ai-shield.my`, and operator identity (`Terry Ong, operating ai-shield`, Malaysia) |
| `/changelog` (and `/ms/changelog`) | Client-facing release notes | Reverse-chronological player-visible product updates (new levels, defence tools, balance/scoring updates, UI changes) with title, date, version/tag, and plain-language summary, separate from the developer `CHANGELOG.md` |
| `/privacy` (and `/ms/privacy`) | Canonical Privacy Policy | Effective date + version; covers `ai-shield.my`, `play.ai-shield.my`, `admin.ai-shield.my`, and `api.ai-shield.my`; full Spec 0058 data, cookie, and browser-storage tables (`shield_player_session` `SameSite=Lax`, `shield_auth_browser`, `shield_session_hint`, `shield_session` `SameSite=Strict` on `admin.ai-shield.my`, `shield_anon_draft:v1:<level>`, `ai-shield:tour-seen:<level>`, `sessionStorage` caches); complete sub-processor list (Supabase, Vercel including Web Analytics and Speed Insights on both `ai-shield.my` and `play.ai-shield.my`, Upstash Redis, Stripe, Resend for transactional/support email, Google Gemini, Groq, TypeSafe, and BYOK providers OpenAI / Anthropic / OpenRouter); Malaysia PDPA 2024 disclosures: bilingual EN/BM notice (s.7(3)), cross-border transfer safeguards, **72-hour mandatory breach notification** to the Personal Data Protection Commissioner (PDPC) and affected users, direct data-processor security obligation, DPO threshold note, data portability via `https://play.ai-shield.my/settings`, and contact `support@ai-shield.my` |
| `/terms` (and `/ms/terms`) | Terms of Service | Effective date + version; individual operator identity (`Terry Ong, operating ai-shield`, Malaysia) and `support@ai-shield.my`; eligibility (13+, parental consent for under-18 paid pass); Acceptable Use Policy (no quota abuse, no attacking platform infrastructure, no uploading others' personal data in custom CSVs); **Educational Simulation Disclaimer** (game boards and scores do not guarantee production LLM security); **BYOK Liability Disclaimer** (Custom Sandbox keys stay in browser memory; user is responsible for provider bills and terms); **AI Output Disclaimer**; `$5 USD` non-renewing 30-day Pass pricing via Stripe; intellectual property; "AS IS" warranty disclaimer and limitation of liability (preserving non-excludable statutory rights); governing law (Malaysia) |
| `/refund` (and `/ms/refund`) | Refund and Cancellation Policy | Standalone page linked in footer; states `$5 USD` 30-day Pass is a one-time non-renewing digital pass activating immediately upon payment; **statutory-minimum policy:** no change-of-mind refunds once activated, **except** full refund or remedy for failed activation, duplicate charges, major unresolved service defects under Malaysia's Consumer Protection Act 1999 (CPA 1999), or where mandatory local law requires otherwise; request steps via `support@ai-shield.my`, **3-business-day** support response SLA, and 5–10 business day Stripe settlement time |
| `/.well-known/security.txt` | Vulnerability disclosure | RFC 9116 file with `Contact: mailto:security@ai-shield.my`, `Preferred-Languages: en, ms`, `Canonical: https://ai-shield.my/.well-known/security.txt`, and `Expires` timestamp |
| Custom error page | 404 / 500 handling | Semantic, accessible error page with link back to `/` and no stack traces |

### 2. Email role mapping

| Address | Role |
| --- | --- |
| `support@ai-shield.my` | General contact, billing/refunds, and privacy/PDPA requests |
| `security@ai-shield.my` | Vulnerability disclosures (`/.well-known/security.txt`) and DMARC reports |
| `no-reply@ai-shield.my` | Transactional auth emails |
| `marketing@ai-shield.my` | Future opt-in product updates |

### 3. Supersession of Spec 0058 web-host criteria

Once `apps/landing` is live and [Spec 0061](../0061-custom-domain-cutover/spec.md) cuts over `play.ai-shield.my`, `WEB-LAND-002` supersedes `WEB-PRIV-001` and `WEB-PRIV-002` from [Spec 0058](../0058-privacy-policy/spec.md) (moving canonical privacy-page hosting and sitemap indexing to `apps/landing`). `WEB-PRIV-003` (data export download in `/settings`) and `API-PRIV-001`–`API-PRIV-004` remain unchanged in `apps/web` and `apps/api`.

## Acceptance criteria

- **WEB-LAND-001**: Given `apps/landing` serves `/`, `/changelog`, `/privacy`, `/terms`, `/refund`, and their `/ms` equivalents, then each route returns `200`, sends baseline security headers (`Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`), includes valid `canonical`, `hreflang`, and Open Graph metadata, and uses semantic HTML landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`, single `<h1>`).
- **WEB-LAND-002**: Given a visitor loads `/privacy` and `/ms/privacy` on `apps/landing`, then both locales include the effective date, policy version, all Spec 0058 data/cookie/storage/sub-processor disclosures (including `shield_anon_draft`, Vercel Web Analytics & Speed Insights, BYOK providers, and Resend), 72-hour PDPC breach notification, cross-border transfer notice, `support@ai-shield.my`, and a working `en` ↔ `ms` locale switcher.
- **WEB-LAND-003**: Given a visitor loads `/terms`, `/refund`, and `/.well-known/security.txt` on `apps/landing`, then `/terms` includes individual operator identity and Malaysia jurisdiction, educational simulation disclaimer, BYOK disclaimer, acceptable use, non-renewing `$5 USD` pass terms, and limitation of liability preserving statutory rights; `/refund` includes CPA 1999 statutory refund guarantees, 3-business-day response SLA, `support@ai-shield.my`, and 5–10 business day Stripe settlement time; and `/.well-known/security.txt` contains `mailto:security@ai-shield.my`.
- **WEB-LAND-004**: Given `apps/landing` loads `/changelog` (and `/ms/changelog`), then release entries render in reverse-chronological order with title, date, version/tag, and plain-language summary.
- **WEB-ACCESS-001**: Given the built `apps/landing` application is audited with `@axe-core/playwright` across `/`, `/changelog`, `/privacy`, `/terms`, and `/refund`, then WCAG 2.2 AA rules pass with zero critical or serious violations.

## Security & privacy considerations

- **No session cookies on root domain:** `apps/landing` sets no authentication cookies; player (`SameSite=Lax`) and admin (`SameSite=Strict`) cookies stay isolated on `play.ai-shield.my` and `admin.ai-shield.my`.
- **No `v-html` on legal pages:** Legal and changelog content renders through safe component/content pipelines to preserve CSP and XSS safety.
- **Analytics alignment:** `apps/landing` enables cookieless Vercel Web Analytics and Speed Insights (matching `apps/web`); CSP and `/privacy` explicitly disclose them, and no advertising or cross-site tracking cookies are loaded.

## Evaluation impact

None. No change to `packages/engine`.

## Open questions

None. (Resolved: Resend is the SMTP/email provider; cookieless Vercel Web Analytics & Speed Insights are enabled on `apps/landing`.)

## Verification

### 2026-11-28 · commit ea6bf79 (+ uncommitted changes)

- Criteria: WEB-LAND-001, WEB-LAND-002, WEB-LAND-003, WEB-LAND-004, WEB-ACCESS-001
- Red: 5 failing test(s) before implementation (`Standalone landing site, bilingual legal pages, and changelog (spec 0060) [WEB-LAND-001] configures security headers, canonical/hreflang/OG metadata, and semantic landmarks`, `Standalone landing site, bilingual legal pages, and changelog (spec 0060) [WEB-LAND-002] provides bilingual EN/BM privacy policy with Spec 0058 disclosures, Resend, BYOK, Vercel Analytics, and 72h PDPC breach notice`, `Standalone landing site, bilingual legal pages, and changelog (spec 0060) [WEB-LAND-003] provides Terms of Service, statutory-minimum Refund Policy, and RFC 9116 security.txt`)
- Green: 5 passing test(s)
- Gate: `mise run check` passed
