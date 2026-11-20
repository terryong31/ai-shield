# Configuration reference

## Gateway (`apps/api`)

Read by [`settings.py`](../../apps/api/src/shield_api/settings.py) (pydantic-settings)
from the process environment and an optional `.env` file in the working directory
(`apps/api/.env` when started with `mise run api:dev`). Names are case-sensitive.
Unknown variables are ignored. Every provider is optional. Template:
[`apps/api/.env.example`](../../apps/api/.env.example).

| Name | Default | Purpose |
| --- | --- | --- |
| `PROJECT_NAME` | `AI S.H.I.E.L.D.` | OpenAPI title and `service` in `/health` |
| `VERSION` | `0.2.0` | OpenAPI version and `version` in `/health` |
| `API_PREFIX` | `/api/v1` | Prefix for all routes, `/docs` and `/openapi.json` |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `APP_ENV` | `production` | `development` serves Swagger UI (`/docs`) and `/openapi.json`; `production` serves neither (ReDoc is always off). `mise run api:dev` sets `development`; Compose defaults to `production`. Other values are rejected at startup. |
| `GROQ_API_KEY` | unset | Runs the game's budget-tier agent (`hard`), and the standard tier (`medium`) when there is no Google key. Unset: those levels use the offline stand-in |
| `GROQ_CHAT_MODEL` | `llama-3.3-70b-versatile` | Groq model for the standard tier when there is no Google key |
| `GOOGLE_API_KEY` | unset | Runs the standard-tier agent (`medium`) on Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for the standard tier |
| `TYPESAFE_API_KEY` | unset | TypeSafe System One (`Jev`) API key (`POST https://api.typesafe.ai/v1/systemone`, also accepted as `JEV_API_KEY`). Unset requires players to enter their Jev API key in `/game` |
| `GAME_MODEL_STANDARD` | unset | Game AI Agent model for `medium` (modern tier). Unset uses `GEMINI_MODEL` with a Google key, else `GROQ_CHAT_MODEL` |
| `GAME_MODEL_BUDGET` | `llama-3.1-8b-instant` | Game AI Agent model for `hard` (budget tier), served by Groq; needs `GROQ_API_KEY` |
| `SUPABASE_URL` | `""` | Supabase project URL. With `SUPABASE_KEY`, admin clearance sessions, players and game data all use Supabase schemas `audit`, `game` and `players` instead of SQLite (spec 0024), and admins sign in with Supabase Auth. Without it nobody can obtain admin clearance |
| `SUPABASE_KEY` | unset | Server-side (service) Supabase key; `mise run admin:create` needs it to set `app_metadata`. Also accepted as `SUPABASE_ANON_KEY` (legacy alias) |
| `SUPABASE_ANON_KEY` | unset | Alias for `SUPABASE_KEY` |
| `WEB_BASE_URL` | `http://localhost:3000` | Public origin of the web client. Confirmation emails link to `<WEB_BASE_URL>/auth/confirmed`, which must be listed in the Supabase project's **Redirect URLs** (spec 0027) |
| `SESSION_TTL_MINUTES` | `480` | Lifetime of a clearance session (spec 0012) |
| `SESSION_COOKIE_SECURE` | `true` | Adds `Secure` to the session cookie. Browsers accept it on `http://localhost`; set `false` only for other plain-HTTP hosts (and Safari on localhost) |
| `CLEARANCE_MAX_ATTEMPTS` | `5` | Failed `POST /clearance` attempts allowed per client address in the window |
| `CLEARANCE_WINDOW_MINUTES` | `10` | Rate-limit window; a failure inside it also yields `DENIED` clearance |
| `SQLITE_PATH` | `var/shield.db` | Base path for the SQLite domain files used when Supabase is not fully configured: `<stem>.audit.db`, `<stem>.game.db` and `<stem>.players.db`, attached as schemas `audit`, `game` and `players` (spec 0024). The Docker image sets `/app/var/shield.db` |
| `REDIS_URL` | `None` | Optional Redis connection URL (e.g. `redis://localhost:6379/0`) for `RedisCachedScoreStore` (`ZSET` + `HASH` leaderboard caching) and Redis Pub/Sub SSE notifications (spec 0028). Degrades gracefully to the underlying `ScoreStore` and in-process SSE notifier when unset or unreachable |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3000,http://[::]:3000` | Comma-separated list of browser origins allowed to call the API with credentials. `*` is rejected |

Secrets (`GROQ_API_KEY`, `GOOGLE_API_KEY`, `SUPABASE_KEY`)
are `SecretStr` and are not printed in logs or reprs.

What degrades without each provider: [Configure LLM providers](../how-to/configure-llm-providers.md#what-degrades-without-each-key).

## Web client (`apps/web`)

| Name | Default | Purpose |
| --- | --- | --- |
| `NUXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Gateway origin, without `/api/v1`. Overrides `runtimeConfig.public.apiBaseUrl` in [`nuxt.config.ts`](../../apps/web/nuxt.config.ts) at runtime. The browser calls this URL directly, so it must be reachable from the user's machine |
| `NUXT_PUBLIC_SITE_URL` | `http://localhost:3000` | Public origin of the web client. Overrides `runtimeConfig.public.siteUrl` in [`nuxt.config.ts`](../../apps/web/nuxt.config.ts) for canonical, Open Graph, Twitter Card, and JSON-LD URLs |
| `PORT` | `3000` (Docker image) | Port of the Nuxt production server |

Template: [`apps/web/.env.example`](../../apps/web/.env.example).

## Engine: `ClassifierDetector`

Keyword arguments, also accepted by `load_baseline(**kwargs)`.

| Name | Default | Purpose |
| --- | --- | --- |
| `malicious_threshold` | `0.85` | Score at or above this is `MALICIOUS` |
| `safe_threshold` | `0.15` | Score at or below this is `SAFE`. Must satisfy `0 <= safe < malicious <= 1` |
| `sensitive_keywords` | `SENSITIVE_KEYWORDS` | Substrings (case-insensitive) that trigger the floor |
| `sensitive_ceiling` | `0.35` | Floor applies only when the score is below this |
| `sensitive_floor` | `0.40` | Score assigned when the floor applies |

`GroqChatModel(api_key, model, *, timeout=30.0)`: request timeout in seconds.
