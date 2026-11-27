# 0058 — Privacy policy and player data controls

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-27
- **Related:** [ADR 0004](../../docs/explanation/decisions/0004-frontend-talks-only-to-gateway.md), [0024-domain-schema-storage](../0024-domain-schema-storage/spec.md), [0025-account-settings](../0025-account-settings/spec.md), [0026-game-only-cleanup](../0026-game-only-cleanup/spec.md), [0046-remove-sqlite-supabase-only](../0046-remove-sqlite-supabase-only/spec.md), [0047-auth-flows-and-hardening](../0047-auth-flows-and-hardening/spec.md), [0049-stripe-pass-checkout](../0049-stripe-pass-checkout/spec.md), [0053-frontend-security-hardening](../0053-frontend-security-hardening/spec.md)

## Problem

`ai-shield` processes player email addresses, passwords (via Supabase Auth), session cookies, saved game boards, public leaderboard scores, custom training CSVs, Stripe pass billing records, IP-based rate-limit hashes, and Vercel web telemetry, yet lacks a user-facing Privacy Policy and self-service data export:

1. **No `/privacy` page or disclosure links.** Players on `/`, `/auth/register`, `/auth/login`, `/plans`, and `/settings` cannot inspect what data is collected, which third-party processors receive it, what cookies are set, or how long data is kept.
2. **No self-service data access / portability endpoint.** Players can reset progress (`POST /api/v1/auth/account/reset-progress`) and delete their account (`DELETE /api/v1/auth/account`), but have no way to download a copy of the personal data `ai-shield` stores for their account.
3. **Deleted accounts' `players.daily_usage` rows persist indefinitely.** `DELETE /api/v1/auth/account` intentionally retains today's `players.daily_usage` count to stop same-day quota-reset abuse, but rows from previous UTC days keyed by the deleted email are never pruned.

## Goals

- Publish a clear, accurate, Nuxt UI-native `/privacy` page whose disclosures match the actual data flows, cookies, third-party processors, and retention schedules in the codebase.
- Surface `/privacy` links across navigation, registration, checkout, and account settings without cluttering the game canvas, and include `/privacy` in SEO indexing (`INDEXABLE_PATHS`, `sitemap.xml`, `llms.txt`).
- Add a self-service **Download my data** export (`GET /api/v1/auth/account/export`) returning the signed-in player's account profile, saved boards, best scores, and purchase summaries as JSON.
- Enforce bounded retention on `players.daily_usage` so deleted or inactive accounts' past-day usage rows do not persist indefinitely after the active UTC day / 30-day abuse-prevention window.

## Non-goals

- Adding a third-party cookie-consent banner (strictly necessary `HttpOnly` auth/session cookies and aggregate cookieless Vercel telemetry do not use advertising or cross-site tracking cookies).
- Changing Stripe Checkout terms, pricing, or Supabase Auth password/email confirmation flows.
- Legal advice or jurisdiction-specific enterprise DPA portals.

## Behaviour

### 1. Public `/privacy` page (`apps/web`)

`apps/web/app/pages/privacy.vue` renders a public, indexable (`robots: 'index, follow'`) Privacy Policy built exclusively with Nuxt UI components (`UPageHeader`, `UPageCard`, `UTable`, `UButton`, `ULink`) and semantic design tokens, showing an **Effective date** and **Policy version**, plus plain-English sections covering:

1. **Summary & Controller:** Who operates `ai-shield`, contact address (configured via `runtimeConfig.public.privacyContactEmail` or documented static contact), and scope.
2. **Data We Collect & Why:**

| Category | Exact data | Purpose & legal basis | Persistence |
| --- | --- | --- | --- |
| Account profile | Email (lowercased), display name (`player_name`), plan tier (`free`/`paid`), `paid_until`, `created_at` | Authentication, quota tiering, leaderboard ownership (contract / legitimate interest) | `players.accounts` + Supabase Auth (`auth.users`) until account deletion |
| Gameplay & saves | Saved board topologies (`game.saved_boards`), best scores/medals (`game.scores`), custom ML training CSVs | Save progress across devices, rank leaderboard, run ML filter | `game.saved_boards` & `game.scores` until reset/deletion; trained ML models kept in ephemeral memory (`1800s` idle TTL) only |
| Wave prompts & BYOK keys | Prompts sent during wave runs; Custom Sandbox BYOK API keys | Evaluate board checks and agent replies in real time | **Never persisted** to DB or browser storage (`audit.requests` was dropped in spec 0026; BYOK keys stay in browser memory only) |
| Billing & passes | `players.purchases` (`id`, `amount_cents`, `currency`, `status`, `payment_intent`, `starts_at`, `ends_at`) | Process 30-day passes via Stripe Checkout, refunds, disputes | Card data stays on Stripe; `email` is set to `NULL` on account deletion while financial record is retained for accounting/chargebacks |
| Security & rate limiting | Client IP (SHA-256 hashed in Redis buckets), `audit.clearance_sessions` token hashes, structured security audit logs | Prevent brute force, bot abuse, and DDoS | Redis rate-limit keys expire in 60s–3600s; spend keys expire in 48h |
| Web telemetry | Aggregate page views and Core Web Vitals via Vercel Web Analytics & Speed Insights | Measure availability and performance | Query strings on `/auth/**` are scrubbed before transmission (spec 0053) |

3. **Cookies & Browser Storage Table:**

| Name | Storage | Purpose | Retention |
| --- | --- | --- | --- |
| `shield_player_session` | `HttpOnly` cookie (`SameSite=Lax`, `Secure` in prod) | Signed-in or anonymous gateway session (stored as SHA-256 hash in `players.sessions`) | Session TTL (or deleted on sign-out / account deletion) |
| `shield_auth_browser` | `HttpOnly` cookie (`SameSite=Lax`) | Binds email confirmation/recovery links to the originating browser (spec 0047) | Short-lived flow TTL (30–60 min) |
| `shield_session_hint` | Cookie (display-only) | Prevents UI flash on initial hydration (holds no email, token, or secrets) | Synced with session; cleared on sign-out |
| `shield_session` | `HttpOnly` cookie (`SameSite=Strict`) | Admin console clearance (`/_console` operators only) | Admin clearance TTL |

4. **Third-Party Sub-processors:** Supabase (Postgres database & Auth), Vercel (hosting, BotID, Web Analytics, Speed Insights), Redis / Upstash (rate limiting, auth-flow state, leaderboard cache), Stripe (hosted checkout & pass billing), and AI inference providers (Google Gemini for standard campaign levels; Groq / OpenAI / Anthropic / OpenRouter when configured or supplied via BYOK).
5. **Your Rights & Controls:** Right to access/export (`/settings` **Download my data**), right to rectify (change display name, email, or password in `/settings`), right to reset progress (`Reset progress`), right to erasure (`Delete account`), and notice on children's privacy (not directed at children under 13 / applicable minimum digital consent age).

### 2. Discoverability & journey notices (`apps/web`)

- Main menu (`/`), `/auth/login`, `/auth/register`, `/plans`, and `/settings` include a link to `/privacy`.
- `/auth/register` displays a short notice below/near the submit action stating that creating an account is subject to the `/privacy` policy.
- `/plans` displays a short notice before checkout noting that payments are processed by Stripe under the `/privacy` policy.
- `app.vue` `INDEXABLE_PATHS`, `apps/web/public/sitemap.xml`, and `apps/web/public/llms.txt` include `/privacy`; `public/robots.txt` permits indexing `/privacy`.

### 3. Self-service data export (`GET /api/v1/auth/account/export`)

- Requires a signed-in, non-anonymous player (`403` for anonymous or unauthenticated callers).
- Rate-limited in production (`ACCOUNT_EXPORT_LIMIT` / `ACCOUNT_EXPORT_WINDOW`, e.g., 5 requests per 15 minutes per account).
- Returns `200` with `Cache-Control: private, no-store` and a structured JSON payload (`AccountExportResponse`):
  - `exported_at` (UTC timestamp)
  - `account`: `email`, `player_name`, `tier`, `paid_until`, `created_at`
  - `saved_boards`: list of `{ level_id, updated_at, save }`
  - `scores`: list of the player's own `game.scores` rows (`level_id`, `total_score`, `medal`, `won`, `mastered`, `attacks_blocked`, `attacks_total`, `false_alarms`, `avg_latency_ms`, `total_cost_usd`, `created_at`)
  - `purchases`: list of the player's own `players.purchases` records (`id`, `amount_cents`, `currency`, `status`, `starts_at`, `ends_at`, `created_at`, `settled_at`) — never `token_hash`, passwords, or other players' data.
- `/settings` adds a **Download my data** row in the Account card that calls `GET /api/v1/auth/account/export` and downloads `ai-shield-account-export.json` via a client `Blob` URL (revoked immediately after click).

### 4. Retention & erasure enforcement (`apps/api`)

- `DELETE /api/v1/auth/account` deletes `game.saved_boards`, `game.scores`, Redis leaderboard entries, ephemeral trained models, `players.sessions`, `players.accounts`, and the Supabase Auth user, sets `players.purchases.email = NULL`, and prunes historical `players.daily_usage` rows for that email where `usage_date < (current UTC date - 30 days)` (retaining only the current UTC window up to 30 days if needed for anti-abuse, or pruning past-day rows on cleanup).
- A helper/maintenance cleanup on `SupabasePlayerStore` prunes `players.daily_usage` rows older than 30 UTC days when deleting accounts or housekeeping expired rows so no deleted player's email stays in `daily_usage` indefinitely.

## Acceptance criteria

- **WEB-PRIV-001**: Given a visitor navigates to `/privacy`, then the page renders using Nuxt UI components only, includes sections for data collected, cookies and browser storage, third-party sub-processors, retention and deletion, and user rights, and sets `robots: 'index, follow'`.
- **WEB-PRIV-002**: Given `/`, `/auth/login`, `/auth/register`, `/plans`, and `/settings`, then each page contains a navigable link to `/privacy`; `/auth/register` and `/plans` show the privacy notice; and `apps/web/public/sitemap.xml`, `apps/web/public/llms.txt`, and `app.vue` `INDEXABLE_PATHS` include `/privacy`.
- **WEB-PRIV-003**: Given a signed-in player on `/settings`, when they click **Download my data**, then the client calls `GET /api/v1/auth/account/export` through `useShieldApi()` and triggers a JSON file download without storing the export in `localStorage` or `sessionStorage`.
- **API-PRIV-001**: Given an unauthenticated or anonymous caller requests `GET /api/v1/auth/account/export`, then the gateway returns `403`; and given a signed-in player requests it, then the gateway returns `200` with `Cache-Control: private, no-store` containing only that player's `account`, `saved_boards`, `scores`, and `purchases` (and never password hashes, session `token_hash`, or other players' rows).
- **API-PRIV-002**: Given `APP_ENV="production"`, when a signed-in player exceeds `ACCOUNT_EXPORT_LIMIT` calls to `GET /api/v1/auth/account/export` within `ACCOUNT_EXPORT_WINDOW`, then the gateway returns `429` with `Retry-After`.
- **API-PRIV-003**: Given a player with `game.saved_boards`, `game.scores`, `players.sessions`, `players.purchases`, and `players.daily_usage` rows (both current UTC day and older than 30 UTC days) executes `DELETE /api/v1/auth/account`, then their boards, scores, sessions, account, and Supabase Auth user are deleted, their `players.purchases.email` is set to `NULL`, and their `players.daily_usage` rows older than 30 UTC days are removed.
- **API-PRIV-004**: Given `GET /api/v1/game/scores` and `GET /api/v1/game/leaderboard` return scores recorded by signed-in players, then no response object or serialized JSON field contains any player `email` address.

## Security & privacy considerations

- **Auth & caching:** `GET /api/v1/auth/account/export` requires a verified non-anonymous `shield_player_session`, is rate-limited in production, and sets `Cache-Control: private, no-store` on both gateway and Nuxt `routeRules`.
- **Least exposure:** Export payloads exclude `token_hash`, `checkout_session_id` / internal Stripe IDs if unnecessary, and all other users' records.
- **Truth in documentation:** Every disclosure on `/privacy` is tied directly to verified schema tables, cookies, and API endpoints so policy drift is caught in code review.
- **No `v-html`:** `/privacy` uses structured Vue templates and Nuxt UI components only, preserving CSP and XSS safety (spec 0053).

## Evaluation impact

None. No change to `packages/engine` scoring or classifiers.

## Open questions

- **Contact email for privacy requests:** Confirm the public privacy contact email (for example `privacy@<domain>` or `runtimeConfig.public.privacyContactEmail`) before setting `Accepted`.

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: WEB-PRIV-001, WEB-PRIV-002, WEB-PRIV-003, API-PRIV-001, API-PRIV-002, API-PRIV-003
- Red: 7 failing test(s) before implementation (`Privacy policy and player data (spec 0058) [WEB-PRIV-001] renders the policy with Nuxt UI, every required section and index robots`, `Privacy policy and player data (spec 0058) [WEB-PRIV-002] links the policy from every key page and lists it for crawlers`, `Privacy policy and player data (spec 0058) [WEB-PRIV-003] downloads the account export as a JSON file without browser storage`)
- Green: 8 passing test(s)
- Gate: `mise run check` passed
