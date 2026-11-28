# 0059 — Admin console extraction and multi-app monorepo support: plan

## 1. Extend monorepo & SDD tooling
- **Root `package.json`:** Change `"workspaces": ["apps/web"]` to `"workspaces": ["apps/*"]`.
- **`scripts/sdd.py`:**
  - Generalize `TEST_PATHS` to `r"(^|/)tests/|^apps/[^/]+/test/|^packages/engine/src/shield_engine/testing\.py$"`.
  - Generalize `PRODUCTION_PATHS` and `PRODUCTION_IN_COMMAND` to cover `apps/[^/]+/(app|server)/`.
  - Update `_run_web` to iterate over all `apps/*` directories that contain a `package.json` and `test/` directory (running `bun run test` in each).
- **Contract generation (`mise run contract`):** Generate `api.gen.ts` once into a shared workspace package (e.g., `packages/api-types/api.gen.ts`) or emit to both `apps/web/app/types/api.gen.ts` and `apps/admin/app/types/api.gen.ts` directly from the `contract` task so generated files are never hand-copied.
- **`scripts/affected.sh` & `scripts/vercel_ignore.sh`:** Add `deploy-admin` target watching `apps/admin/**`, `contracts/**`, and root workspace files; document `admin` in `vercel_ignore.sh`.
- **`mise.toml` & `.github/workflows/ci.yml`:** Add `admin:dev` (port `3002`), `test:admin`, `lint:admin`, `typecheck:admin`, wire them into `mise run test`, `lint`, `typecheck`, `check`, and add the `admin` job to `.github/workflows/ci.yml`.

## 2. Extract `/_console` into `apps/admin`
- Scaffold minimal Nuxt 4 + Nuxt UI app in `apps/admin/`.
- Move:
  - `apps/web/app/pages/console/index.vue` → `apps/admin/app/pages/index.vue`
  - `apps/web/app/pages/console/settings.vue` → `apps/admin/app/pages/settings.vue`
  - `apps/web/app/layouts/dashboard.vue` → `apps/admin/app/layouts/dashboard.vue`
  - `apps/web/app/composables/useAdminAccess.ts` → `apps/admin/app/composables/useAdminAccess.ts`
- Add `apps/admin/server/routes/api/v1/[...path].ts` forwarding `x-shield-admin-proxy-secret` (`runtimeConfig.apiAdminProxySecret`) to `runtimeConfig.apiProxyTarget`.
- Configure `apps/admin/nuxt.config.ts` with `X-Robots-Tag: noindex, nofollow`, `Cache-Control: no-store`, and strict CSP/security headers on `/**`, plus `apps/admin/public/robots.txt` (`User-agent: *\nDisallow: /`).
- Remove `/_console` files and route rules from `apps/web`, and migrate the `/_console` tests from `apps/web/test/` to `apps/admin/test/`.

## 3. Backend admin proxy guard (`apps/api`)
- Add `API_ADMIN_PROXY_SECRET` to `apps/api/src/shield_api/settings.py` (required in production alongside `API_PROXY_SECRET`).
- Enforce the admin proxy secret on admin clearance and admin-only routers in production.
- Add `https://admin.ai-shield.my` to `CORS_ORIGINS` in production, and update `apps/api/src/shield_api/admin_cli.py` to print `https://admin.ai-shield.my`.

## 4. Vercel project for `apps/admin`
- Create a Vercel project with Root Directory `apps/admin`, Ignored Build Step `bash ../../scripts/vercel_ignore.sh admin`, custom domain `admin.ai-shield.my`, and Vercel Deployment Protection enabled.
