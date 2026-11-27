# 0053 — Frontend security hardening: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

All changes stay inside `apps/web` and keep logic testable as pure functions in `app/utils/` and `shared/utils/`:

1. **Security headers (`shared/utils/securityHeaders.ts` + `nuxt.config.ts`):**
   - Extract header builders (`buildSecurityHeaders({ isProd })`, `buildRouteSecurityRules({ isProd })`) into `apps/web/shared/utils/securityHeaders.ts` so Vitest can assert every header directly and `nuxt.config.ts` consumes the exact same object in `routeRules`.
   - Include `Content-Security-Policy` with directives compatible with Nuxt 4, Vue Flow, BotID, and Vercel Analytics/Speed Insights.
   - Set `Cache-Control: no-store` on `/auth/**`, `/_console`, `/_console/**`, `/settings`, and `/plans`.
2. **Auth error allowlist & analytics scrubbing (`app/utils/playerAuth.ts`, `app/utils/analytics.ts`, `app/pages/auth/confirmed.vue`, `app/pages/auth/reset-password.vue`):**
   - Add `authLinkErrorMessage(errorCode, fallback)` in `app/utils/playerAuth.ts` and replace raw `errorDescription` usage in `confirmed.vue` and `reset-password.vue`.
   - Add `sanitizeAnalyticsEvent(event)` in `app/utils/analytics.ts` and wire it into Vercel Analytics `beforeSend` (or plugin config) to strip query strings on `/auth/**`.
3. **Proxy hardening (`shared/utils/apiProxy.ts`):**
   - Add `maxBodyBytes` option (default `2 * 1024 * 1024`) to `ProxyGatewayOptions`. Check `Content-Length` first, then read the request body with a bounded reader so chunked transfers cannot bypass the cap; return `413` on overflow.
   - Tighten CSRF verification in `proxyToGateway`: reject any `sec-fetch-site` value other than `same-origin` or `none`, and when `requireProxyTrust` is `true`, require either a matching `Origin` or `Sec-Fetch-Site: same-origin`.
4. **Admin console (`app/pages/console/index.vue`, `app/utils/account.ts`):**
   - Gate `loadScores()` behind a `watch(() => access.value.allowed, ...)` with `{ immediate: true }` instead of unconditional `onMounted(loadScores)`.
   - Add `clearScoreboardConfirmed(text: string): boolean` (`text === 'CLEAR'`) and a confirmation `UModal` around `handleClearScores`.
5. **Defence-in-depth & hygiene (`app/utils/billing.ts`, `app/utils/seo.ts`, `app/pages/plans.vue`, `app/app.vue`, `app/pages/settings.vue`, `public/robots.txt`, `package.json`):**
   - Add `isAllowedCheckoutUrl(raw: string): boolean` in `app/utils/billing.ts` and call it in `plans.vue` before `navigateTo(url, { external: true })`.
   - Add `serializeJsonLd(data: unknown): string` in `app/utils/seo.ts` (escaping `<` to `\u003c`) and use it in `app.vue`.
   - Add `emailChangeSchema` in `app/utils/account.ts` and bind `:schema="emailChangeSchema"` on the Change Email `UForm` in `settings.vue`.
   - Remove `Disallow: /_console` from `apps/web/public/robots.txt`.
   - Pin `"latest"` `devDependencies` in `apps/web/package.json` to current lockfile semver ranges.

## Interfaces

```ts
// apps/web/shared/utils/securityHeaders.ts
export function buildSecurityHeaders(options: { isProd: boolean }): Record<string, string>
export function buildRouteSecurityRules(options: { isProd: boolean }): Record<string, { headers: Record<string, string> }>

// apps/web/shared/utils/apiProxy.ts
export const DEFAULT_MAX_BODY_BYTES = 2 * 1024 * 1024
export interface ProxyGatewayOptions {
  // ...existing fields
  maxBodyBytes?: number
}

// apps/web/app/utils/playerAuth.ts
export function authLinkErrorMessage(errorCode: string | null, fallback: string): string

// apps/web/app/utils/billing.ts
export function isAllowedCheckoutUrl(raw: string): boolean

// apps/web/app/utils/seo.ts
export function serializeJsonLd(data: unknown): string

// apps/web/app/utils/account.ts
export const emailChangeSchema: z.ZodObject<{ email: z.ZodEmail, password: z.ZodString }>
export function clearScoreboardConfirmed(text: string): boolean
```

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New configuration is documented in `docs/reference/configuration.md` (if any env var is added; none expected)

## Alternatives considered

| Option | Why not |
| --- | --- |
| Put security headers only in `apps/web/vercel.json` | Docker/Node deployments (`apps/web/Dockerfile`) ignore `vercel.json`; `nuxt.config.ts` `routeRules` covers both Vercel and Node. |
| Install `nuxt-security` module | Adds a new dependency and opinionated middleware that can conflict with BotID and Nitro proxy streaming; `routeRules` + pure helpers keep dependencies minimal and directly testable. |

## Risks and rollback

- **CSP blocking runtime scripts or styles:** If a third-party script (BotID or Vercel Analytics) or inline style is blocked in preview, inspect browser console CSP reports and adjust the directive in `shared/utils/securityHeaders.ts` before promoting to production.
- **Strict CSRF check breaking non-browser test clients:** Only enforce missing-header rejection when `requireProxyTrust` is `true` (production), keeping local dev and direct test requests unaffected.
- **Rollback:** Revert the commit; no database schema or API contract changes are involved.
