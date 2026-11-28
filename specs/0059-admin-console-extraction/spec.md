# 0059 — Admin console extraction and multi-app monorepo support

- **Status:** Implemented
- **Area:** DEV | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-28
- **Related:** [0010-enforced-sdd-tdd-workflow](../0010-enforced-sdd-tdd-workflow/spec.md), [0012-clearance-sessions](../0012-clearance-sessions/spec.md), [0041-same-origin-api-proxy](../0041-same-origin-api-proxy/spec.md), [0053-frontend-security-hardening](../0053-frontend-security-hardening/spec.md), [0060-landing-site-and-legal](../0060-landing-site-and-legal/spec.md), [0061-custom-domain-cutover](../0061-custom-domain-cutover/spec.md)

## Problem

The operator admin console (`/_console`) currently lives inside `apps/web` alongside the public game client, and the repository's SDD, workspace, contract, and CI tooling only recognizes a single JavaScript app (`apps/web`):

1. **Shared blast radius for admin UI.** Shipping `/_console` inside `apps/web` bundles admin pages with player code and prevents independent deployment protection or host-level cookie isolation on `admin.ai-shield.my`.
2. **Single-app JS tooling.** `scripts/sdd.py` only guards `apps/web/app/` and `apps/web/test/` and only runs Vitest in `apps/web`; root `package.json` only lists `"apps/web"` in `workspaces`; and CI, Vercel ignore scripts, and contract generation do not support additional `apps/*` Nuxt applications.

## Goals

- Extend SDD guards, workspace configuration, Vercel build-skipping, contract generation, and CI workflows so the monorepo cleanly supports multiple `apps/*` JavaScript applications (`apps/web`, `apps/admin`, and upcoming `apps/landing`).
- Extract `/_console` out of `apps/web` into an isolated `apps/admin` application deployed to `https://admin.ai-shield.my`.
- Scope the admin session cookie (`shield_session`, `SameSite=Strict`, `HttpOnly`, `Secure`) strictly to `admin.ai-shield.my` and prevent `apps/web` from proxying to admin endpoints.

## Non-goals

- Building the marketing landing site (`apps/landing`, covered in [Spec 0060](../0060-landing-site-and-legal/spec.md)).
- Switching `apps/web` or `apps/api` production domains, DNS, Supabase Auth, or Stripe webhooks (covered in [Spec 0061](../0061-custom-domain-cutover/spec.md)).
- Changing admin authentication logic or clearance TTLs in `apps/api`.

## Behaviour

### 1. Multi-app monorepo and SDD support

- SDD path guards treat `apps/*/app/` (and `apps/*/server/`) as production code and `apps/*/test/` as test code across all JS apps.
- `sdd:red` and `sdd:green` execute Vitest in every `apps/*` workspace that contains matching tests.
- Contract generation writes OpenAPI TypeScript types from a single source of truth without hand-copied generated files.
- CI and Vercel build-skipping evaluate `apps/web`, `apps/admin`, and `apps/api` independently so changes to one app do not rebuild unaffected apps.

### 2. Isolated admin console (`apps/admin`)

- `apps/admin` serves the guarded admin dashboard at `/` and settings at `/settings` (removing the `/_console` path prefix).
- Every route on `apps/admin` returns `X-Robots-Tag: noindex, nofollow`, `Cache-Control: no-store`, and baseline security headers, and `robots.txt` disallows all crawlers (`Disallow: /`).
- `apps/admin` proxies `/api/v1/**` server-side to the gateway using a dedicated admin proxy credential so `apps/web` cannot forward requests to admin clearance or admin-only routes in production.
- `apps/web` removes all `/_console` routes, layouts, and admin composables; requests to `/_console` on `apps/web` return `404`.
- The operator CLI (`admin_cli.py`) directs operators to sign in at `https://admin.ai-shield.my`.

## Acceptance criteria

- **DEV-SDD-001**: Given a cycle targets criteria in `apps/admin` or any other `apps/*` JS workspace, when `scripts/sdd.py` evaluates path guards and runs `sdd:red`/`sdd:green`, then `apps/*/app/` is guarded as production code, `apps/*/test/` is allowed in the red phase, and Vitest runs in every matching `apps/*` workspace.
- **DEV-CI-001**: Given root `package.json`, `scripts/affected.sh`, `scripts/vercel_ignore.sh`, `mise.toml`, `mise run contract`, and `.github/workflows/ci.yml`, then `apps/admin` is registered in workspaces, CI, contract type generation, and Vercel deploy filtering without duplicating hand-maintained contract files.
- **WEB-ADMIN-001**: Given `/_console` has been extracted, when `apps/web` is inspected or receives a request for `/_console`, then no `/_console` route or admin console module exists in `apps/web` and `/_console` returns `404`.
- **WEB-ADMIN-002**: Given `apps/admin` serves `/` and `/settings`, then every route requires a granted admin session, sets `robots: 'noindex, nofollow'`, sends `X-Robots-Tag: noindex, nofollow` and `Cache-Control: no-store`, disallows crawling in `robots.txt`, and proxies `/api/v1/**` same-origin.
- **API-ADMIN-001**: Given `APP_ENV=production`, when a request to an admin clearance or admin-only endpoint arrives without the dedicated admin proxy secret (or from a non-admin origin), then the gateway rejects it with `403`, while a valid request from `https://admin.ai-shield.my` with the admin proxy secret succeeds.

## Security & privacy considerations

- **Origin & cookie isolation:** Moving `/_console` to `admin.ai-shield.my` scopes `shield_session` (`HttpOnly`, `SameSite=Strict`, `Secure`) strictly to `admin.ai-shield.my`, completely isolated from `play.ai-shield.my` and `ai-shield.my`.
- **Proxy boundary enforcement:** Separating `API_ADMIN_PROXY_SECRET` from the public web proxy secret ensures a compromise or SSRF in `apps/web` cannot reach admin clearance endpoints.
- **Defense in depth:** Require Vercel Deployment Protection (or IP allowlist) on the `apps/admin` Vercel project in production so unauthenticated internet traffic cannot reach the admin login form.

## Evaluation impact

None. No change to `packages/engine`.

## Open questions

None. (Resolved: enforce dedicated `API_ADMIN_PROXY_SECRET` on admin routes in production plus Vercel Deployment Protection on `admin.ai-shield.my`, following OWASP ASVS access-control isolation and Malaysia PDPA Security Principle s.9.)

## Verification

### 2026-11-28 · commit ea6bf79 (+ uncommitted changes)

- Criteria: DEV-SDD-001, DEV-CI-001, WEB-ADMIN-001, WEB-ADMIN-002, API-ADMIN-001
- Red: 5 failing test(s) before implementation (`scripts/tests/test_admin_extraction_tooling.py::test_sdd_guards_and_discovers_all_apps_js_workspaces`, `scripts/tests/test_admin_extraction_tooling.py::test_monorepo_config_includes_apps_admin`, `Admin console extraction (spec 0059) [WEB-ADMIN-001] removes /_console routes and admin modules from apps/web`)
- Green: 10 passing test(s)
- Gate: `mise run check` passed
