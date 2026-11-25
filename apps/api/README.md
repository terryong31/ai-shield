# shield-api: game gateway

A thin FastAPI service that puts the [`shield-engine`](../../packages/engine)
game on the network for the [web client](../web). It contains **no detection
or scoring logic**. Its job is to:

1. own players: anonymous sessions, accounts, plans and daily run quotas (`/api/v1/auth/*`),
2. run the game: levels, wave runs, the custom BYOK sandbox and ML filter training (`/api/v1/game/*`),
3. keep saved boards and the leaderboard,
4. guard the admin console with a clearance session for Supabase users whose
   `app_metadata.role` is `"admin"` (`/api/v1/clearance`, `mise run admin:create`),
5. wire the agent models (Gemini standard tier, Groq budget tier) and persistence
   in Supabase (`SUPABASE_URL` and `SUPABASE_KEY`). The schema lives in
   [`supabase/migrations`](../../supabase/migrations).

```
src/shield_api/
├── main.py          # create_app(): CORS, routers, docs only in development
├── container.py     # composition root: wires adapters from Settings
├── settings.py      # environment configuration
├── schemas.py       # HTTP models (the public contract)
├── routers/         # health, auth, game, clearance
├── services/        # players, scores, sessions, clearance, identity, admins
└── providers/       # Gemini adapter, BYOK provider allowlist
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

- [HTTP API](../../docs/reference/http-api.md)
- [Configuration](../../docs/reference/configuration.md)
- Specs: [0007 Gateway HTTP API](../../specs/0007-gateway-http-api/spec.md), [0016 game](../../specs/0016-game-engine/spec.md), [0026 game-only cleanup](../../specs/0026-game-only-cleanup/spec.md)
