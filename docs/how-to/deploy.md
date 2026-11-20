# Deploy

The gateway and the web client ship as two Docker images. Both Dockerfiles
expect the **repository root** as build context, because they need the
workspace lockfiles and, for the gateway, the engine package.

## Run everything with Docker Compose

For a single host, `compose.yaml` at the repo root runs both images:

```bash
cp apps/api/.env.example apps/api/.env   # optional; loaded if present
mise run up                              # docker compose up --build
```

- web: http://localhost:3000; api: http://localhost:8000/api/v1/health (Compose runs `APP_ENV=production`, so `/api/v1/docs` is off; start with `APP_ENV=development mise run up` to enable it)
- `web` starts once `api` passes its health check.
- Game data is SQLite in the named volume `shield-data` (mounted at
  `/app/var`), so it survives `mise run down` and rebuilds. `docker compose down -v` deletes it.
- To use the local Supabase stack from the container, set
  `SUPABASE_URL=http://host.docker.internal:54321` in `apps/api/.env`.
- If the browser reaches the API at another address, set `PUBLIC_API_URL`
  (and `CORS_ORIGINS` for the web origin) before `docker compose up`.

The sections below cover building and configuring the images yourself.

## 1. Build the images

```bash
docker build -f apps/api/Dockerfile -t ai-shield-api .
docker build -f apps/web/Dockerfile -t ai-shield-web .
```

| Image | Base | Contents | Runs as | Port |
| --- | --- | --- | --- | --- |
| `ai-shield-api` | `python:3.12-slim-bookworm` | `.venv` with `shield-api` and `shield-engine` (non-editable, no dev deps) | `shield` (uid 10001) | 8000 |
| `ai-shield-web` | `node:24-slim` | Nuxt `.output` | `node` | 3000 |

The gateway starts
`uvicorn shield_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers`.
The web image starts `node .output/server/index.mjs`.

## 2. Configure the gateway

Pass configuration as environment variables. The image contains no `.env`
(`.dockerignore` excludes it). Full list: [Configuration](../reference/configuration.md).

| Variable | Needed for |
| --- | --- |
| `CORS_ORIGINS` | **Required in practice.** The web client's public origin(s), comma-separated, e.g. `https://shield.example.com`. The default only allows `http://localhost:3000` |
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | The standard-tier agent (Medium) |
| `GROQ_API_KEY`, `GAME_MODEL_BUDGET` | The budget-tier agent (Hard), and Medium without Gemini ([how-to](configure-llm-providers.md)) |
| `SUPABASE_URL`, `SUPABASE_KEY` | Persistent game data ([how-to](persist-game-data.md)) and admin accounts; without them nobody can open the admin console |
| `WEB_BASE_URL` | The web client's public origin, for the email confirmation link (add `<WEB_BASE_URL>/auth/confirmed` to Supabase **Redirect URLs**) |
| `APP_ENV` | Leave unset (`production`) so Swagger UI and `/openapi.json` stay off |
| `LOG_LEVEL` | Optional |

Without Supabase, mount a volume on `/app/var` so the SQLite files survive
restarts, and run a single replica (SQLite is a single-writer file):

```bash
docker run -d --name shield-api -p 8000:8000 \
  -v shield-data:/app/var \
  -e CORS_ORIGINS=https://shield.example.com \
  -e GROQ_API_KEY="$GROQ_API_KEY" \
  -e SUPABASE_URL="$SUPABASE_URL" -e SUPABASE_KEY="$SUPABASE_KEY" \
  ai-shield-api
```

## 3. Configure the web client

| Variable | Value |
| --- | --- |
| `NUXT_PUBLIC_API_BASE_URL` | The gateway's public origin **as seen from the user's browser**, without `/api/v1`, e.g. `https://api.shield.example.com`. Read at runtime; no rebuild needed |
| `PORT` | Defaults to `3000` |

```bash
docker run -d --name shield-web -p 3000:3000 \
  -e NUXT_PUBLIC_API_BASE_URL=https://api.shield.example.com \
  ai-shield-web
```

The browser calls the gateway directly, so the gateway must be publicly
reachable at that URL and list the web origin in `CORS_ORIGINS`.

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

Then open the web client and run a wave on Easy; a CORS error in the browser
console means `CORS_ORIGINS` or `NUXT_PUBLIC_API_BASE_URL` is wrong.

## Production hardening checklist

Before exposing the game beyond a trusted network:

- [ ] **Create the admin accounts** with `mise run admin:create <email>` (it
      prompts for the password and sets `app_metadata.role = "admin"`), using a
      long unique password. Remove access with `mise run admin:revoke <email>`.
- [ ] **Set up custom SMTP in Supabase** (Authentication → Emails → SMTP), or
      confirmation emails reach only your project team.
- [ ] **Leave `APP_ENV` unset** (production), so the API docs and schema are not served.
- [ ] **Terminate TLS** at a reverse proxy or load balancer. `--proxy-headers`
      is enabled, so run the gateway only behind a proxy you control.
- [ ] **Rate-limit `POST /api/v1/auth/*` and `POST /api/v1/game/run`** per client
      at the proxy. Daily quotas cap runs per session, but anonymous sessions are
      cheap to create, and login is not throttled by the gateway.
- [ ] **Pick the storage backend deliberately.** SQLite is a single-writer file:
      fine for one replica with a persistent volume at `/app/var`. For several
      replicas or managed backups, use Supabase ([persist game data](persist-game-data.md)).
- [ ] Store secrets in your platform's secret manager, not in image layers or
      committed files.
- [ ] Review [Threat model](../explanation/threat-model.md) known gaps.
