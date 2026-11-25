# Deploy

The gateway and the web client ship as two Docker images. Both Dockerfiles
expect the **repository root** as build context, because they need the
workspace lockfiles and, for the gateway, the engine package.

## Run everything with Docker Compose

For a single host, `compose.yaml` at the repo root runs both images:

```bash
infisical login                          # once per machine
mise run up                              # docker compose up --build
```

- web: http://localhost:3000; api: http://localhost:8000/api/v1/health (Compose defaults to `APP_ENV=development`; run `APP_ENV=production mise run up` to test production mode)
- `web` starts once `api` passes its health check.
- `mise run up` runs Compose with Infisical `dev /api` ([Manage secrets](manage-secrets.md)) and rewrites
  local Supabase to `SUPABASE_URL=http://host.docker.internal:54421` with the local `SUPABASE_KEY`.
  `compose.yaml` gives the `api` container only `APP_ENV`, `CORS_ORIGINS`, `REDIS_URL`, `SUPABASE_URL` and
  `SUPABASE_KEY`. Put other variables (provider and Stripe keys) in `apps/api/.env`.
- The browser only talks to `web`; it proxies `/api/v1/**` to `api` over the
  Compose network (`NUXT_API_PROXY_TARGET=http://api:8000`).

The sections below cover building and configuring the images yourself.

## 1. Build the images

```bash
docker build -f apps/api/Dockerfile -t ai-shield-api .
docker build -f apps/web/Dockerfile -t ai-shield-web .
```

| Image | Base | Contents | Runs as | Port |
| --- | --- | --- | --- | --- |
| `ai-shield-api` | `python:3.12-slim-bookworm` | `.venv` with `shield-api` and `shield-engine` (non-editable, no dev deps) | `shield` (uid 10001) | 8000 |
| `ai-shield-web` | `node:25-slim` | Nuxt `.output` | `node` | 3000 |

The gateway starts
`uvicorn shield_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers`.
The web image starts `node .output/server/index.mjs`.

## 2. Configure the gateway

Pass configuration as environment variables. The image contains no `.env`
(`.dockerignore` excludes it). Full list: [Configuration](../reference/configuration.md).

| Variable | Needed for |
| --- | --- |
| `CORS_ORIGINS` | Optional. The browser calls the web server, which proxies to the gateway server-to-server, so CORS is not exercised. Set it only if a browser calls the gateway directly |
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | The standard-tier agent (Medium) |
| `GROQ_API_KEY`, `GAME_MODEL_BUDGET` | The budget-tier agent (Hard), and Medium without Gemini ([how-to](configure-llm-providers.md)) |
| `SUPABASE_URL`, `SUPABASE_KEY` | **Required.** Persistent game data ([how-to](persist-game-data.md)), player accounts, and admin clearance |
| `WEB_BASE_URL` | The web client's public origin, for the email confirmation link (add `<WEB_BASE_URL>/auth/confirmed` and `<WEB_BASE_URL>/auth/reset-password` to Supabase **Redirect URLs**) |
| `APP_ENV` | Leave unset (`production`) so Swagger UI and `/openapi.json` stay off |
| `REDIS_URL`, `TRUSTED_CLIENT_IP_HEADER`, `TRUSTED_PROXY_SECRET` | **Required** in production (spec 0043) |
| `MODEL_SIGNING_KEY` | `POST /game/train` in production (spec 0045) |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | The 30-day pass ([how-to](accept-payments.md)) |
| `LOG_LEVEL` | Optional |

```bash
docker run -d --name shield-api -p 8000:8000 \
  -e GROQ_API_KEY="$GROQ_API_KEY" \
  -e SUPABASE_URL="$SUPABASE_URL" -e SUPABASE_KEY="$SUPABASE_KEY" \
  ai-shield-api
```

## 3. Configure the web client

| Variable | Value |
| --- | --- |
| `NUXT_API_PROXY_TARGET` | **Required.** The gateway's origin **as seen from the web server**, without `/api/v1`, e.g. `http://shield-api:8000` or `https://ai-shield-api.vercel.app`. Server-only; read at runtime. Unset means `http://localhost:8000`, and a wrong value answers every API call with `502` |
| `NUXT_PUBLIC_SITE_URL` | The web client's public origin, for canonical and social links |
| `PORT` | Defaults to `3000` |

```bash
docker run -d --name shield-web -p 3000:3000 \
  -e NUXT_API_PROXY_TARGET=http://shield-api:8000 \
  ai-shield-web
```

The browser calls only the web server's own `/api/v1/**`, which proxies to the
gateway (spec 0041). Session cookies are therefore first-party even when the two
run on different sites, such as two `*.vercel.app` hosts.

## Deploy on Vercel

Create two Vercel projects from the same repository. Keep the secrets in Infisical `prod` (`/api` and
`/web`) and bring them to the Vercel projects ([Manage secrets](manage-secrets.md)).

**Apply database migrations before you merge to `main`** (`mise run db:remote:plan`, then
`mise run db:remote:push`). Vercel deploys `main` immediately.

| Project | Root Directory | Notes |
| --- | --- | --- |
| API | `apps/api` | FastAPI preset; entrypoint comes from `[tool.vercel]` in `apps/api/pyproject.toml`. Keep "Include files outside the Root Directory" on (the engine and `uv.lock` live outside it) |
| Web | `apps/web` | Nuxt preset. Set `NUXT_API_PROXY_TARGET` to the API project's production URL and `NUXT_PUBLIC_SITE_URL` to the web URL |

API environment: `SUPABASE_URL`, `SUPABASE_KEY`, `REDIS_URL`, and `TRUSTED_PROXY_SECRET` are **required** in production, along with `TRUSTED_CLIENT_IP_HEADER=x-shield-client-ip`, `WEB_BASE_URL` (the web URL), and `GOOGLE_API_KEY` / `GROQ_API_KEY`. On Web Vercel, set `NUXT_API_PROXY_SECRET` to match the API secret, confirm `NUXT_CLIENT_IP_HEADER=x-vercel-forwarded-for` (also the Nuxt default; production fails closed without a resolved header IP), and keep Vercel BotID enabled on the project (spec 0043). Leave `APP_ENV` unset (`production`).

To sell passes, do [Accept payments](accept-payments.md).

## 4. Health check

```
GET /api/v1/health
```

Returns 200 with `"status": "healthy"` once the app has started and loaded the
model. Use it for container and load-balancer health checks. Check
`agent_tiers` to confirm the provider keys were picked up and `storage_backend`
for the store in use. The images define no Docker `HEALTHCHECK`; configure it in your
orchestrator.

## 5. Verify

```bash
curl -s https://api.shield.example.com/api/v1/health
curl -s https://api.shield.example.com/api/v1/game/levels | head -c 200
```

Then open the web client and run a wave on Easy. `curl https://<web>/api/v1/health`
should return the same JSON as the gateway; a `502` means `NUXT_API_PROXY_TARGET`
is wrong or the gateway is down.

## Production hardening checklist

Before exposing the game beyond a trusted network:

- [ ] **Create the admin accounts** with `mise run admin:remote:create <email>` (it
      prompts for the password and sets `app_metadata.role = "admin"`), using a
      long unique password. Remove access with `mise run admin:remote:revoke <email>`.
- [ ] **Set up custom SMTP in Supabase** (Authentication → Emails → SMTP), or
      confirmation emails reach only your project team.
- [ ] **Leave `APP_ENV` unset** (production), so the API docs and schema are not served.
- [ ] **Terminate TLS** at a reverse proxy or load balancer. `--proxy-headers`
      is enabled, so run the gateway only behind a proxy you control.
- [ ] **Set `REDIS_URL`.** The gateway rate limits (sign-in, anonymous sessions, runs,
      training, email, checkout) need it to work across instances
      ([Configuration](../reference/configuration.md), `APP_ENV`).
- [ ] **Expose the Supabase domain schemas** (`audit`, `game`, `players`) in Data API settings ([persist game data](persist-game-data.md)).
- [ ] Keep secrets in Infisical, not in image layers or committed files.
- [ ] **Before real payments**, do the steps in [Go live](accept-payments.md#go-live).
- [ ] Review [Threat model](../explanation/threat-model.md) known gaps.
