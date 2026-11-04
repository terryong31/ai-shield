# shield-api: demo gateway

A thin FastAPI service that puts the [`shield-engine`](../../packages/engine)
on the network for the [web demo](../web). It contains **no detection logic**.
Its job is to:

1. map HTTP requests to engine calls (session cookie → `Clearance`, mode → `ShieldConfig`),
2. stream engine events to the browser as NDJSON (`/api/v1/chat`),
3. expose the `ai-shield` workflow game endpoints (`/api/v1/game/levels`, `/api/v1/game/train-classifier`, `/api/v1/game/run`, `/api/v1/game/scores`),
4. run the *protected application*: a demo assistant with a simulated
   enterprise toolbox, gated by the engine's tool policy,
5. own persistence: clearance sessions, leaderboard scores, and the audit log go to SQLite (`var/shield.db`) by default,
   or to Supabase when `SUPABASE_URL` and `SUPABASE_KEY` are set. The schema
   lives in [`supabase/migrations`](../../supabase/migrations).

```
src/shield_api/
├── main.py          # create_app(): CORS, routers, OpenAPI stream schemas
├── container.py     # composition root: wires adapters from Settings
├── settings.py      # environment configuration
├── schemas.py       # HTTP models + ChatEvent protocol (the public contract)
├── routers/         # health, screening, chat, feedback, audit, clearance, game
├── services/        # chat flow, access mapping, sessions, audit log
└── demo/            # the protected app: assistant, tools, Gemini adapter
```

## Run

```bash
cp .env.example .env        # optional
mise run api:dev            # from the repo root → http://localhost:8000/api/v1/docs
```

## Test

```bash
mise run test:api
```

The HTTP contract is committed at
[`contracts/shield-api.openapi.json`](../../contracts/shield-api.openapi.json).
After changing any schema, run `mise run contract` and commit the result;
a test fails if it drifts.

## Reference

- [HTTP API and stream events](../../docs/reference/http-api.md)
- [Configuration](../../docs/reference/configuration.md)
- Spec: [0007 Gateway HTTP API](../../specs/0007-gateway-http-api/spec.md)
