# AGENTS.md: apps/web

The game client. Root rules in [../../AGENTS.md](../../AGENTS.md) apply; these add to them.

## Map

| Path | Responsibility |
| --- | --- |
| `app/composables/useShieldApi.ts` | The only backend client (auth, game and admin endpoints) |
| `app/utils/gameBoard.ts` | Pure board graph builder, node catalog, hop trace folding, and console access guard |
| `app/utils/customSandbox.ts` | Custom sandbox limits, dataset CSV parsing and access rules (spec 0022); never stores the API key |
| `app/utils/sessionHint.ts`, `app/plugins/sessionHint.client.ts` | Display-only session cookie for the first render; never an authority |
| `app/utils/anonDraft.ts` | Anonymous board drafts in `localStorage` (spec 0052): wiring and positions only, never scores |
| `app/utils/billing.ts` | Pass wait and end-date rules (spec 0049) |
| `app/types/api.gen.ts` | **Generated** from the contract. Never edit; run `mise run contract` |
| `app/types/api.ts` | Friendly aliases over the generated types |
| `app/components/workflow/GameNode.vue` | The game board's Vue Flow node |
| `app/pages/index.vue` | Game main menu, level selector cards, and leaderboard |
| `app/pages/settings.vue` | Player settings: theme, display name, email, password, data export, reset, delete |
| `app/pages/auth/` | Player authentication pages (`login`, `register`, `recover`, `confirmed`, `reset-password`) |
| `app/pages/game.vue` | Layout of the defence board page: header, panels and SEO (at most 600 lines, spec 0055) |
| `app/composables/useGamePage.ts` | All state and logic of the game page; `provide`d by the page, read by panels with `useGameContext()` |
| `app/components/game/` | Game page panels: controls, tools panel, canvas, dialogs, results, node settings, tour |
| `app/pages/plans.vue` | Free and Paid plans (`UPricingPlans`), pass checkout and sync |
| `public/` | `llms.txt`, `robots.txt` and `sitemap.xml` use the production URL; update them when pages, levels or the price change (WEB-GAME-017) |

## Rules

- UI: use **Nuxt 4, Nuxt UI and Vue Flow components only**. Style with Nuxt UI
  semantic tokens (`text-muted`, `bg-elevated`, `border-default`), not raw
  palette colours, unless you are extending an existing node style. When
  unsure about a component API, consult the Nuxt UI docs or MCP server.
- Data: only through `useShieldApi()`. No Supabase or other data clients, and no secrets in `runtimeConfig.public`.
- Put logic worth testing in `app/utils/` as pure functions, and test it in `test/*.test.ts` with spec IDs in the test names.
- No `any`. Type Vue Flow refs as `Ref<Node[]>` (see `WorkflowVisualizer.vue`).
- Follow Nuxt UI writing standard. Check for latest documentation at https://ui.nuxt.com/ . For componenets check https://ui.nuxt.com/docs/components

## Security rules and anti-patterns

Follow these rules on every change to `apps/web` to prevent common frontend vulnerabilities:

- **Never weaken or bypass global security headers.** Define `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, and production `Strict-Transport-Security` in `nuxt.config.ts` `routeRules` (not only `vercel.json`, so Docker/Node deployments match Vercel). Always set `Cache-Control: no-store` on auth, settings, billing, and admin routes.
- **Never render untrusted URL query parameters as UI messages.** Do not display `route.query.error_description` or other free-text query params directly (content spoofing / phishing). Map known error codes to a static allowlist of strings.
- **Never let auth tokens linger in URLs or reach analytics.** Strip one-time auth query params (`code`, `token_hash`, `flow`) immediately and ensure client analytics (`@vercel/analytics`, `@vercel/speed-insights`) scrub query strings on `/auth/**`.
- **Never redirect externally to an unvalidated URL.** Before calling `navigateTo(url, { external: true })` or assigning `window.location`, validate the URL scheme (`https:`) and host against an explicit allowlist (for example `checkout.stripe.com`).
- **Never use raw HTML sinks or unescaped `<script>` serialization.** Do not use `v-html`, `innerHTML`, `eval`, or `new Function`. When serializing JSON-LD into `<script type="application/ld+json">`, always escape `<` as `\u003c`.
- **Never store secrets or session tokens in browser storage.** Session cookies are `HttpOnly` and owned by the gateway. Never put tokens, passwords, or user API keys (`customApiKey`) in `localStorage`, `sessionStorage`, non-`HttpOnly` cookies, or `runtimeConfig.public`.
- **Never buffer unbounded bodies or accept loose origins in the Nitro proxy.** Enforce a byte cap before reading request bodies in `shared/utils/apiProxy.ts`. On state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`), reject `cross-site` and `same-site` requests and fail closed in production when origin headers are missing.
- **Never trigger destructive actions on one click or fetch admin data before clearance.** Destructive admin or account actions must require an explicit confirmation modal (typed confirmation word or re-authentication). Gate admin API calls on `access.allowed`.
- **Never advertise private routes in `public/robots.txt`.** Use `useSeoMeta({ robots: 'noindex, nofollow' })` on private routes instead of listing them in `robots.txt`. Admin routes live in `apps/admin`, not `apps/web`.
- **Always validate forms with Zod and pin package versions.** Every `UForm` that submits user input must bind a Zod `:schema`. Never use `"latest"` in `apps/web/package.json` dependencies or `devDependencies`.

Also please use UEmpty for empty states, and USplitter for resizable layouts.

Bad code example:
```js
<UModal>
  <template #content>
  <!-- header  -->
  <div>
  Something here
  </div>
  <!-- body  -->
  <div>
  Something here
  </div>
  <!-- footer  -->
  <div>
  Something here
  </div>
</UModal>
```
Good code example:
```js
<UModal>
  <template #header>
  Something here
  </template>

  <template #body>
  Something here
  </template>

  <template #footer>
  Something here
  </template>
</UModal>
```

## Commands

```bash
mise run web:dev
mise run test:web
bun run --cwd apps/web lint:fix
mise run typecheck:web
```
