# Configuration reference

## Gateway (`apps/api`)

Read by [`settings.py`](../../apps/api/src/shield_api/settings.py) (pydantic-settings)
from the process environment and an optional `.env` file in the working directory
(`apps/api/.env` when started with `mise run api:dev`). The mise tasks put the Infisical
variables into the environment, and they override `.env`
([Manage secrets](../how-to/manage-secrets.md)). Names are case-sensitive.
Unknown variables are ignored. Every model provider is optional. Template:
[`apps/api/.env.example`](../../apps/api/.env.example).

| Name | Default | Purpose |
| --- | --- | --- |
| `PROJECT_NAME` | `AI S.H.I.E.L.D.` | OpenAPI title and `service` in `/health` |
| `VERSION` | `0.2.0` | OpenAPI version and `version` in `/health` |
| `API_PREFIX` | `/api/v1` | Prefix for all routes, `/docs` and `/openapi.json` |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `APP_ENV` | `production` | `development` serves Swagger UI (`/docs`) and `/openapi.json`; `production` serves neither (ReDoc is always off), requires `REDIS_URL`, enables gateway rate limits (IP auth `30/5m`, failed login `10/15m`, anon `30/h`, recover/resend `1/60s`, run `30/m` IP & `10/m` session, train `10/m`), and enforces Vercel BotID headers on protected POST routes (spec 0043). `mise run api:dev`, Compose (`mise run up`) and `apps/api/.env.example` use `development`; the Vercel deployment uses `production`. Other values are rejected at startup |
| `GROQ_API_KEY` | unset | Runs the game's budget-tier agent (`hard`), and the standard tier (`medium`) when there is no Google key. Unset: those levels use the offline stand-in |
| `GROQ_CHAT_MODEL` | `openai/gpt-oss-120b` | Groq model for the standard tier when there is no Google key |
| `GOOGLE_API_KEY` | unset | Runs the standard-tier agent (`medium`) on Gemini |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model for the standard tier |
| `TYPESAFE_API_KEY` | unset | TypeSafe System One (`Jev`) API key (`POST https://api.typesafe.ai/v1/systemone`, also accepted as `JEV_API_KEY`). Unset requires players to enter their Jev API key in `/game` |
| `GAME_MODEL_STANDARD` | unset | Game AI Agent model for `medium` (modern tier). Unset uses `GEMINI_MODEL` with a Google key, else `GROQ_CHAT_MODEL` |
| `GAME_MODEL_BUDGET` | `openai/gpt-oss-20b` | Game AI Agent model for `hard` (budget tier), served by Groq; needs `GROQ_API_KEY` |
| `SUPABASE_URL` | `""` | **Required.** Supabase project URL. With `SUPABASE_KEY`, admin clearance sessions, players and game data use Supabase schemas `audit`, `game` and `players`, and admins/players sign in with Supabase Auth (spec 0046). Missing or partial config raises `ConfigurationError` at startup |
| `SUPABASE_KEY` | unset | **Required.** Server-side (service) Supabase key; `mise run admin:create` needs it to set `app_metadata`. Also accepted as `SUPABASE_ANON_KEY` (legacy alias) |
| `SUPABASE_ANON_KEY` | unset | Alias for `SUPABASE_KEY` |
| `WEB_BASE_URL` | `http://localhost:3000` | Public origin of the web client. **Required** and must not be `localhost`/`127.0.0.1` when `APP_ENV=production` (spec 0047); production also requires `https://` (spec 0054). Its origin is accepted as an `Origin` on state-changing requests, together with `CORS_ORIGINS`. Confirmation, email-change, and password-recovery emails link to `<WEB_BASE_URL>/auth/confirmed` and `<WEB_BASE_URL>/auth/reset-password`, which must be listed in the Supabase project's **Redirect URLs** |
| `SESSION_TTL_MINUTES` | `480` | Lifetime of player and clearance sessions (specs 0012, 0016) |
| `SESSION_COOKIE_SECURE` | `true` | Adds `Secure` to the session cookie. Browsers accept it on `http://localhost`; set `false` only for other plain-HTTP hosts (and Safari on localhost). Must be `true` in production (spec 0054) |
| `ALLOW_SELF_UPGRADE` | `false` | Enables `POST /api/v1/auth/upgrade` and the Paid upgrade button on `/plans` for demos. When `false`, upgrades answer `403` and `/plans` shows `Coming soon` (spec 0042). Must be `false` in production (spec 0054) |
| `TRUSTED_CLIENT_IP_HEADER` | unset | Header name carrying the real client IP, e.g. `x-shield-client-ip` behind the Nuxt proxy. The gateway reads it only when the request proves `TRUSTED_PROXY_SECRET`, and then takes the **last** comma-separated entry, the hop that the proxy added (spec 0054). Otherwise it uses the socket address. **Required** when `APP_ENV=production` (`build_container` raises `ConfigurationError` if unset) (spec 0043) |
| `TRUSTED_PROXY_SECRET` | unset | Shared secret (`x-shield-proxy-secret`) checked in constant time. In production **every** request except `GET /api/v1/health` and `POST /api/v1/billing/webhook` must carry it, or the gateway answers `403 Request blocked.` (spec 0054). It also unlocks the trusted IP header and BotID-vouched requests. **Required** when `APP_ENV=production` (`build_container` raises `ConfigurationError` if unset) (spec 0043) |
| `CLEARANCE_MAX_ATTEMPTS` | `5` | Failed `POST /clearance` attempts allowed per client address in the window |
| `CLEARANCE_WINDOW_MINUTES` | `10` | Rate-limit window; a failure inside it also yields `DENIED` clearance |
| `REDIS_URL` | `None` | Optional in development (`http`/`memory`), **required** in `production`, where it must use `rediss://` (TLS, spec 0054). Redis connection URL (e.g. `redis://localhost:6379/0`) for `RateLimiter` (spec 0043), `LeaderboardService` sorted sets + Lua updates (`lb:v<ver>:*`, spec 0044), and `RedisTrainedModelStore` (`mlmodel:*`, spec 0045). When unset or unreachable in development, reads fall back to the paginated score store with a 10 s in-process cache |
| `MODEL_SIGNING_KEY` | unset | Server secret for HMAC-SHA256 verification of temporary server-held trained ML models (spec 0045). Unset generates an ephemeral per-process key in development; in `production`, `POST /game/train` answers `503` and an error is logged at startup. In production a key shorter than 32 bytes counts as unset (spec 0054) |
| `STRIPE_SECRET_KEY` | unset | Stripe key (`sk_test_`, `rk_test_`, `sk_live_` or `rk_live_`) for the 30-day pass (spec 0049). Unset: billing is off and `/plans` shows `Coming soon`. Another prefix stops startup |
| `STRIPE_WEBHOOK_SECRET` | unset | Signing secret of the webhook endpoint (`whsec_`). **Required** when `STRIPE_SECRET_KEY` is set |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3000,http://[::]:3000` | Comma-separated list of browser origins allowed to call the API with credentials. `*` is rejected. Not exercised when the browser goes through the web proxy (spec 0041) |

Secrets (`GROQ_API_KEY`, `GOOGLE_API_KEY`, `TYPESAFE_API_KEY`, `SUPABASE_KEY`, `REDIS_URL`, `MODEL_SIGNING_KEY`,
`TRUSTED_PROXY_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`)
are `SecretStr` and are not printed in logs or reprs.

What degrades without each provider: [Configure LLM providers](../how-to/configure-llm-providers.md#failure-behaviour).

## Web client (`apps/web`)

| Name | Default | Purpose |
| --- | --- | --- |
| `NUXT_API_PROXY_TARGET` | `http://localhost:8000` | Gateway origin, without `/api/v1`, as reached **from the web server**. Overrides the private `runtimeConfig.apiProxyTarget` in [`nuxt.config.ts`](../../apps/web/nuxt.config.ts) at runtime. The browser calls same-origin `/api/v1/**` and the web server proxies it here (spec 0041); never sent to the browser. Must be `http(s)`; otherwise every API call answers `502` |
| `NUXT_API_PROXY_SECRET` | `""` | Server-only shared secret forwarded as `x-shield-proxy-secret` matching gateway `TRUSTED_PROXY_SECRET`. **Required** in production (`VERCEL=1` or `NODE_ENV=production` with `APP_ENV!=development`; missing value returns `503`) (spec 0043) |
| `NUXT_CLIENT_IP_HEADER` | `"x-vercel-forwarded-for"` | Incoming header name (for example `x-vercel-forwarded-for`) to extract the client IP and forward as `x-shield-client-ip`. **Required** in production, with no socket-address fallback (`503` if unset or missing on the request) (spec 0043) |
| `NUXT_PUBLIC_PRIVACY_CONTACT_EMAIL` | `""` | Contact address on `/privacy` (spec 0058). Empty shows a link to the project issues page instead |
| `NUXT_PUBLIC_SITE_URL` | `http://localhost:3000` | Public origin of the web client. Overrides `runtimeConfig.public.siteUrl` in [`nuxt.config.ts`](../../apps/web/nuxt.config.ts) for canonical, Open Graph, Twitter Card, and JSON-LD URLs |
| `PORT` | `3000` (Docker image) | Port of the Nuxt production server |

Template: [`apps/web/.env.example`](../../apps/web/.env.example).

### Security headers and the proxy (spec 0053)

[`app/utils/securityHeaders.ts`](../../apps/web/app/utils/securityHeaders.ts) gives the `routeRules` of `nuxt.config.ts`:

| Route | Headers |
| --- | --- |
| `/**` | `Content-Security-Policy` (`default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`. A production build (`NODE_ENV=production`) also sends `Strict-Transport-Security`. |
| `/auth/**` | `Referrer-Policy: no-referrer`, `Cache-Control: no-store` |
| `/settings`, `/plans` | `Cache-Control: no-store` |

The isolated admin console (`apps/admin`, `admin.ai-shield.my`) sets `X-Robots-Tag: noindex, nofollow`, `Cache-Control: no-store`, strict CSP, and HSTS in production, and proxies `/api/v1/**` with `NUXT_API_ADMIN_PROXY_SECRET` (`x-shield-admin-proxy-secret`). The landing site (`apps/landing`, `ai-shield.my`) sets CSP, security headers, and HSTS in production via [`apps/landing/app/utils/securityHeaders.ts`](../../apps/landing/app/utils/securityHeaders.ts).

The `/api/v1/**` proxy refuses a body over 2 MiB with `413` before it calls the gateway, also when the request has no `Content-Length`. It refuses a `POST`, `PUT`, `PATCH` or `DELETE` with `403 Cross-site request blocked.` when `Sec-Fetch-Site` is not `same-origin` or `none`, when `Origin` is another origin, or, in production, when both headers are missing.

Vercel Web Analytics and Speed Insights load from the client plugin `app/plugins/analytics.client.ts`. Each event goes through `scrubAnalyticsEvent`, which removes the query string from `/auth/**` URLs.

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
