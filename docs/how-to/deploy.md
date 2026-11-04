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

- web: http://localhost:3000; api: http://localhost:8000/api/v1/docs
- `web` starts once `api` passes its health check.
- The audit log is SQLite in the named volume `shield-data` (mounted at
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
| `SECURE_PASSPHRASE` | Set it, or no caller can get `GRANTED` clearance. Treat it as a secret |
| `GROQ_API_KEY` (+ `GROQ_*_MODEL`) | Moderation and Layer 2. Without it, Layer 2 falls back to `RESTRICTED` |
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | Assistant answers |
| `SUPABASE_URL`, `SUPABASE_KEY` | Persistent audit log ([how-to](persist-the-audit-log.md)) |
| `FEEDBACK_PATH` | Preset to `/app/var/feedback.csv` in the image |
| `LOG_LEVEL` | Optional |

### Persist reviewer feedback

Reviewer labels are appended to `FEEDBACK_PATH` and reloaded at startup. Mount
a volume on `/app/var` so they survive restarts, and run only one gateway
replica per feedback file (the CSV is cached in each process and appended to
without locking):

```bash
docker run -d --name shield-api -p 8000:8000 \
  -v shield-feedback:/app/var \
  -e CORS_ORIGINS=https://shield.example.com \
  -e SECURE_PASSPHRASE="$SECURE_PASSPHRASE" \
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
`moderation_enabled` and `adjudication_enabled` to confirm the Groq key was
picked up. The images define no Docker `HEALTHCHECK`; configure it in your
orchestrator.

## 5. Verify

```bash
curl -s https://api.shield.example.com/api/v1/health
curl -s -X POST https://api.shield.example.com/api/v1/screen \
  -H 'Content-Type: application/json' -d '{"message":"drop table employees"}'
```

The second call should return `"blocked": true` and `"layer": "LAYER_1_ML"`.
Then open the web client and send a prompt; a CORS error in the browser console
means `CORS_ORIGINS` or `NUXT_PUBLIC_API_BASE_URL` is wrong.

## Production hardening checklist

The gateway is a demo. Before exposing it beyond a trusted network:

- [ ] **Set `SECURE_PASSPHRASE`** to a long random value from your secret
      store, or remove passphrase-based clearance from your deployment. It is a
      stand-in for RBAC: one shared secret, sent in request bodies, and stored
      in the browser's `localStorage` by the web client.
- [ ] **Put real authentication in front of the gateway** (an identity-aware
      proxy, API gateway or OAuth2 middleware). The API has no authentication:
      anyone who can reach it can use `/chat`, read `/requests` and submit
      `/feedback`, which overrides classifier verdicts.
- [ ] **Terminate TLS** at a reverse proxy or load balancer. `--proxy-headers`
      is enabled, so run the gateway only behind a proxy you control.
- [ ] **Rate-limit** `/chat`, `/screen` and `/feedback` per client at the proxy.
      Each Layer 2 request can make five LLM calls; without limits, cost is
      unbounded (denial of wallet).
- [ ] **Pick the audit backend deliberately.** SQLite is a single-writer file:
      fine for one replica with a persistent volume at `/app/var`. For several
      replicas or managed backups, use Supabase ([persist the audit log](persist-the-audit-log.md)).
- [ ] **Restrict `/feedback` and `/requests`** to reviewers. A feedback label
      is an exact-text override of the classifier.
- [ ] **Decide `default_policy`.** Prompts Layer 1 finds `SAFE` get `ALLOW_ALL`
      by default. For deny-by-default tool access, construct the `Shield` with
      `ShieldConfig(default_policy=ToolPolicy.RESTRICTED)` in `container.py`.
- [ ] **Consider `fail_closed=True`** for moderation if you rely on it.
- [ ] Store secrets in your platform's secret manager, not in image layers or
      committed files.
- [ ] Review [Threat model](../explanation/threat-model.md) known gaps.
