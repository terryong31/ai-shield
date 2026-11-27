# 0058 — Privacy policy and player data controls: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Deliver the public privacy policy page, cross-app links, self-service JSON export, and retention pruning across `apps/api` and `apps/web` (with OpenAPI contract regeneration):

1. **Backend export & retention (`apps/api`):**
   - **Schemas (`schemas.py`):** Add `AccountExportAccount`, `AccountExportBoard`, `AccountExportScore`, `AccountExportPurchase`, and `AccountExportResponse` (`GET /api/v1/auth/account/export`), then run `mise run contract` to update `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.
   - **Store methods (`services/players.py`, `services/scores.py`):**
     - Add `list_boards_for(email)` and `list_purchases_for(email)` to `PlayerStore` (implemented on both `InMemoryPlayerStore` and `SupabasePlayerStore`).
     - Reuse `ScoreStore.list_scores_for_owner(email)` for the player's best scores.
     - In `SupabasePlayerStore.delete_account(email)` (and `InMemoryPlayerStore.delete_account(email)`), delete `players.daily_usage` rows for `email` with `usage_date < (today - 30 days)` while preserving the recent window against same-day quota abuse.
   - **Router (`routers/account.py`):** Add `GET /auth/account/export` gated by `_player()`, rate-limited in production (`ACCOUNT_EXPORT_LIMIT = 5`, `ACCOUNT_EXPORT_WINDOW = 900` in `services/rate_limit.py`), setting `Cache-Control: private, no-store`, and emitting an audit log entry (`account_export`).
2. **Frontend `/privacy` page, links & export UI (`apps/web`):**
   - **Page (`app/pages/privacy.vue`):** Build a monochrome, Nuxt UI-only page (`UPageHeader`, `UPageCard`, `UTable`, `UButton`, `ULink`) documenting data categories, cookies/storage, sub-processors, retention, and player rights, with `buildPageSeo({ title: 'Privacy Policy', path: '/privacy', ... })`.
   - **Links & notices:** Add `/privacy` links on `/` (subtle footer link in the left main-menu column), `/auth/login`, `/auth/register` (with short privacy acknowledgement text), `/plans` (with Stripe processing notice), and `/settings`.
   - **Data export UI (`app/pages/settings.vue`, `app/composables/useShieldApi.ts`):** Add `exportAccount()` in `useShieldApi.ts` and a **Download my data** action in the Account card on `/settings` that creates a temporary `Blob` download (`ai-shield-account-export.json`) and revokes the object URL immediately.
   - **SEO & static files:** Add `/privacy` to `INDEXABLE_PATHS` in `app/app.vue`, `apps/web/public/sitemap.xml`, and `apps/web/public/llms.txt`. Add `privacyContactEmail` to `runtimeConfig.public` in `nuxt.config.ts` (defaulting cleanly without exposing any secret).

## Interfaces

New HTTP endpoint in `apps/api/src/shield_api/routers/account.py`:

```python
@router.get("/export", responses={403: ..., 429: ..., 503: ...})
async def export_account(
    request: Request, response: Response, container: ContainerDep
) -> AccountExportResponse: ...
```

New `PlayerStore` protocol methods in `apps/api/src/shield_api/services/players.py`:

```python
async def list_boards_for(self, email: str) -> list[SavedBoardSummary]: ...
async def list_purchases_for(self, email: str) -> list[PurchaseSummary]: ...
```

Contract regeneration required: run `mise run contract` after editing `schemas.py`.

## Boundaries check

- [x] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [x] `apps/web` still talks to the backend only through the published OpenAPI contract (`useShieldApi()` + `api.gen.ts`)
- [ ] New `runtimeConfig.public.privacyContactEmail` (if added) is documented in `docs/reference/configuration.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Static Markdown or external Google Doc for privacy policy | External docs drift from the app theme and break offline/self-hosted deployments; a first-party `/privacy` Nuxt page matches the monochrome UI, works offline/locally, and is testable with Vitest/Playwright. |
| Emailing data exports asynchronously | Adds background email delivery complexity and exposes PII over SMTP; synchronous JSON download over HTTPS with `Cache-Control: private, no-store` is immediate and keeps data off email servers. |

## Risks and rollback

- **Policy accuracy drift:** Future changes to cookies, sub-processors, or tables must update `apps/web/app/pages/privacy.vue` alongside the spec/code change.
- **Large export payloads:** Each account can hold at most 19 campaign saves + 1 custom save (capped at 256 KiB each) and ~20 scores, so total export JSON is bounded (< 5 MiB) and fast to serialize.
- **Rollback:** Revert `privacy.vue`, footer/page links, and the `GET /auth/account/export` route, and regenerate `contracts/shield-api.openapi.json`.
