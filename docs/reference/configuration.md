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
| `GROQ_API_KEY` | unset | Enables Llama Guard moderation, the Analyst/Warden debate, and Groq as the assistant's fallback chat model. Unset: no moderation; Layer 2 uses the conservative fallback |
| `GROQ_GUARD_MODEL` | `llama-guard-3-8b` | Groq model for moderation |
| `GROQ_DEBATE_MODEL` | `llama-3.3-70b-versatile` | Groq model for the debate |
| `GROQ_CHAT_MODEL` | `llama-3.3-70b-versatile` | Groq model for assistant answers (tried after Gemini) |
| `GOOGLE_API_KEY` | unset | Enables Gemini as the assistant's primary chat model |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for assistant answers |
| `GAME_MODEL_STANDARD` | unset | Game AI Agent model for `medium` (modern tier). Unset uses `GEMINI_MODEL` with a Google key, else `GROQ_CHAT_MODEL` |
| `GAME_MODEL_BUDGET` | `llama-3.1-8b-instant` | Game AI Agent model for `hard` (budget tier), served by Groq; needs `GROQ_API_KEY` |
| `SUPABASE_URL` | `""` | Supabase project URL. With `SUPABASE_KEY`, the audit log, clearance sessions, players and game data all use Supabase schemas `audit`, `game` and `players` instead of SQLite (spec 0024) |
| `SUPABASE_KEY` | unset | Server-side Supabase key. Also accepted as `SUPABASE_ANON_KEY` (legacy alias) |
| `SUPABASE_ANON_KEY` | unset | Alias for `SUPABASE_KEY` |
| `SECURE_PASSPHRASE` | unset | Passphrase accepted by `POST /clearance`. Unset: no caller can obtain `GRANTED` |
| `SESSION_TTL_MINUTES` | `480` | Lifetime of a clearance session (spec 0012) |
| `SESSION_COOKIE_SECURE` | `true` | Adds `Secure` to the session cookie. Browsers accept it on `http://localhost`; set `false` only for other plain-HTTP hosts (and Safari on localhost) |
| `CLEARANCE_MAX_ATTEMPTS` | `5` | Failed `POST /clearance` attempts allowed per client address in the window |
| `CLEARANCE_WINDOW_MINUTES` | `10` | Rate-limit window; a failure inside it also yields `DENIED` clearance |
| `SQLITE_PATH` | `var/shield.db` | Base path for the SQLite domain files used when Supabase is not fully configured: `<stem>.audit.db`, `<stem>.game.db` and `<stem>.players.db`, attached as schemas `audit`, `game` and `players` (spec 0024). The Docker image sets `/app/var/shield.db` |
| `FEEDBACK_PATH` | `var/feedback.csv` | CSV file where reviewer labels are appended (relative to the working directory). The Docker image sets `/app/var/feedback.csv` |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3000,http://[::]:3000` | Comma-separated list of browser origins allowed to call the API with credentials. `*` is rejected |

Secrets (`GROQ_API_KEY`, `GOOGLE_API_KEY`, `SUPABASE_KEY`, `SECURE_PASSPHRASE`)
are `SecretStr` and are not printed in logs or reprs.

What degrades without each provider: [Configure LLM providers](../how-to/configure-llm-providers.md#what-degrades-without-each-key).

## Web client (`apps/web`)

| Name | Default | Purpose |
| --- | --- | --- |
| `NUXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Gateway origin, without `/api/v1`. Overrides `runtimeConfig.public.apiBaseUrl` in [`nuxt.config.ts`](../../apps/web/nuxt.config.ts) at runtime. The browser calls this URL directly, so it must be reachable from the user's machine |
| `PORT` | `3000` (Docker image) | Port of the Nuxt production server |

Template: [`apps/web/.env.example`](../../apps/web/.env.example).

## Engine: `ShieldConfig`

Passed to `Shield(..., config=)` or per call to `screen(..., config=)`.

| Name | Default | Purpose |
| --- | --- | --- |
| `always_adjudicate` | `False` | Send every non-blocked prompt to Layer 2 (gateway mode `guardrail`) |
| `skip_classifier` | `False` | Ablation: do not call Layer 1; treat it as SAFE/0.0 (gateway mode `chaos`) |
| `default_policy` | `ToolPolicy.ALLOW_ALL` | Tool policy for prompts that were not adjudicated |

## Engine: `ClassifierDetector`

Keyword arguments, also accepted by `load_baseline(**kwargs)`.

| Name | Default | Purpose |
| --- | --- | --- |
| `malicious_threshold` | `0.85` | Score at or above this is `MALICIOUS` |
| `safe_threshold` | `0.15` | Score at or below this is `SAFE`. Must satisfy `0 <= safe < malicious <= 1` |
| `sensitive_keywords` | `SENSITIVE_KEYWORDS` | Substrings (case-insensitive) that trigger the floor |
| `sensitive_ceiling` | `0.35` | Floor applies only when the score is below this |
| `sensitive_floor` | `0.40` | Score assigned when the floor applies |
| `feedback` | `None` | `FeedbackStore` whose exact-text labels override the model |

## Engine: other constructor options

| Class | Option | Default | Purpose |
| --- | --- | --- | --- |
| `LlamaGuardModerator` | `fail_closed` | `False` | On provider error, flag with category `ERROR` instead of passing |
| `DebateAdjudicator` | `temperature` | `0.3` | Sampling temperature for debate calls |
| `GroqChatModel` | `timeout` | `30.0` | Request timeout in seconds |

## CLI environment (`shield-engine eval --pipeline full`)

| Name | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | required | Exits with an error when missing |
| `GROQ_GUARD_MODEL` | `llama-guard-3-8b` | Moderation model |
| `GROQ_DEBATE_MODEL` | `llama-3.3-70b-versatile` | Debate model |
