# HTTP API reference

The game gateway (`apps/api`, version 0.2.0). Source of truth:
[`schemas.py`](../../apps/api/src/shield_api/schemas.py) and the committed contract
[`contracts/shield-api.openapi.json`](../../contracts/shield-api.openapi.json).
Specs: [0007](../../specs/0007-gateway-http-api/spec.md) (gateway), [0012](../../specs/0012-clearance-sessions/spec.md) (admin clearance),
[0016](../../specs/0016-game-engine/spec.md) and [0020](../../specs/0020-game-ai-agent/spec.md)–[0023](../../specs/0023-game-saved-boards/spec.md) (game),
[0026](../../specs/0026-game-only-cleanup/spec.md) (game-only surface).

- Base path: `/api/v1` (setting `API_PREFIX`).
- Interactive docs: `GET /api/v1/docs` (Swagger UI) and `GET /api/v1/openapi.json`, only when `APP_ENV=development` (`mise run api:dev`). In production (the default) both return `404`. ReDoc is always disabled. The committed contract is `contracts/shield-api.openapi.json`.
- Request bodies are JSON (`Content-Type: application/json`).
- The web client also keeps a display-only `shield_session_hint` cookie. The gateway ignores it.
- Players authenticate with the `shield_player_session` cookie (`/auth/*`). The admin
  console uses a separate clearance cookie from `POST /clearance`; see [Clearance](#clearance).
- CORS: origins from `CORS_ORIGINS` (a `*` is rejected at startup), credentials allowed.
  Browser clients must send `credentials: 'include'` so the session cookies travel.

## Status codes

| Code | When |
| --- | --- |
| 200 / 201 / 204 | Success |
| 401 | Wrong credentials, or an admin route without clearance |
| 403 | The player's tier cannot do this (for example saving while anonymous) |
| 404 | Unknown resource, or a removed or production-disabled route |
| 413 | Saved board too large |
| 422 | Request validation failed. Body is FastAPI's `HTTPValidationError`: `{"detail": [{"type", "loc", "msg", "input", "ctx"?}]}` |
| 429 | Daily run quota or clearance attempt limit reached |
| 502 | The player's own model provider failed (custom sandbox) |

## Request gate and response headers (spec 0054)

Every response has `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. Production adds `Strict-Transport-Security: max-age=31536000; includeSubDomains`. Responses under `/api/v1/auth/`, `/api/v1/clearance`, `/api/v1/game/saves/`, `/api/v1/game/progress`, `/api/v1/game/leaderboard/me` and `/api/v1/billing/` (not the webhook) have `Cache-Control: private, no-store`.

Before a route runs:

- **Production proxy secret:** every request except `GET /api/v1/health` and `POST /api/v1/billing/webhook` must carry `x-shield-proxy-secret`; otherwise `403 {"detail": "Request blocked."}`.
- **Cross-site requests:** a `POST`, `PUT`, `PATCH` or `DELETE` (not the webhook) is `403 {"detail": "Cross-site request blocked."}` when `Sec-Fetch-Site` is not `same-origin` or `none`, when `Origin` is not in `CORS_ORIGINS` or the `WEB_BASE_URL` origin, or, in production, when it carries a session cookie and neither header.
- **Body size:** the body of a state-changing request is read with a limit of 256 KiB (1.25 MiB on `/api/v1/game/train`), also without `Content-Length`. Over the limit: `413 {"detail": "Request body too large."}`.
- **Validation errors:** a `422` lists each error without its `input`, `ctx` or `url`, so a password or token is never sent back.

Request models reject unknown fields (`422`). Board ids are at most 128 characters; a node `config` has at most 32 keys, 4 levels of nesting and 16 KiB of JSON; `positions` has at most 60 entries; a training `csv_text` is at most 1,310,720 characters, `dataset` at most 2,000 rows, and a row `text` at most 4,000 characters.

## Routes

| Method | Path | Request | Response | Codes |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/health` | none | `HealthResponse` | 200 |
| POST | `/api/v1/clearance` | `ClearanceRequest` | `ClearanceStatus` | 200, 401, 422, 429 |
| GET | `/api/v1/clearance` | none | `ClearanceStatus` | 200 |
| DELETE | `/api/v1/clearance` | none | empty | 204 |
| GET | `/api/v1/auth/session` | none | `PlayerSessionStatus` | 200 |
| POST | `/api/v1/auth/anonymous` | none | `PlayerSessionStatus` | 200 |
| POST | `/api/v1/auth/register` | `PlayerRegisterRequest` | `PlayerSessionStatus` or `PlayerConfirmationResponse` | 200, 202, 422, 429, 503 |
| POST | `/api/v1/auth/confirm` | `PlayerConfirmRequest` | `PlayerConfirmResponse` | 200, 400, 403, 422, 503 |
| POST | `/api/v1/auth/login` | `PlayerLoginRequest` | `PlayerSessionStatus` | 200, 401, 403, 422, 429, 503 |
| POST | `/api/v1/auth/resend-confirmation` | `PlayerResendRequest` | `PlayerConfirmationResponse` | 202, 403, 422, 429 |
| POST | `/api/v1/auth/account/password` | `AccountPasswordRequest` | `PlayerSessionStatus` | 200, 401, 403, 422, 429, 503 |
| PATCH | `/api/v1/auth/account/profile` | `AccountProfileRequest` | `PlayerSessionStatus` | 200, 403, 422, 429, 503 |
| POST | `/api/v1/auth/account/email` | `AccountEmailRequest` | `PlayerConfirmationResponse` | 202, 401, 403, 409, 422, 429, 503 |
| GET | `/api/v1/auth/account/export` | none | `AccountExportResponse` | 200, 403, 429, 503 |
| POST | `/api/v1/auth/account/reset-progress` | `AccountResetRequest` | `AccountResetResponse` | 200, 401, 403, 422, 429, 503 |
| DELETE | `/api/v1/auth/account` | `AccountDeleteRequest` | none | 204, 401, 403, 422, 429, 503 |
| POST | `/api/v1/auth/recover` | `PlayerRecoverRequest` | `PlayerRecoverResponse` | 200, 403, 422, 429 |
| POST | `/api/v1/auth/reset-password` | `PlayerResetPasswordRequest` | `PlayerResetPasswordResponse` | 200, 400, 403, 422, 503 |
| POST | `/api/v1/auth/upgrade` | none | `PlayerSessionStatus` | 200, 403 |
| POST | `/api/v1/auth/logout` | none | empty | 204 |
| POST | `/api/v1/billing/checkout` | none | `BillingCheckoutResponse` | 200, 403, 409, 429, 503 |
| POST | `/api/v1/billing/sync` | `BillingSyncRequest` | `BillingSyncResponse` | 200, 403, 422, 429, 503 |
| POST | `/api/v1/billing/webhook` | signed Stripe event | none | 200, 400, 503 |
| GET | `/api/v1/game/levels` | none | `GameCatalogResponse` | 200 |
| POST | `/api/v1/game/train` | `GameTrainRequest` | `GameTrainResponse` | 200, 403, 413, 422, 429, 503 |
| DELETE | `/api/v1/game/models` | none (player cookie) | empty | 204 |
| POST | `/api/v1/game/models/purge` | none (player cookie beacon) | empty | 204 |
| POST | `/api/v1/game/run` | `GameRunRequest` | `GameRunResponse` | 200, 400, 403, 422, 429, 502, 503 |
| GET | `/api/v1/game/saves/{level_id}` | path `level_id` | `SavedBoardResponse` | 200, 403, 404 |
| PUT | `/api/v1/game/saves/{level_id}` | `SavedBoardRequest` | `SavedBoardResponse` | 200, 403, 413, 422 |
| GET | `/api/v1/game/leaderboard` | query `difficulty`, `limit` (1–100) | `DifficultyLeaderboardEntry[]` | 200, 422 |
| GET | `/api/v1/game/leaderboard/me` | query `difficulty` | `LeaderboardRankResponse` | 200, 403, 422 |
| GET | `/api/v1/game/progress` | none | `PlayerProgressResponse` | 200 |
| GET | `/api/v1/game/scores` | query `level_id`, `limit` (1–100) | `ScoreRecord[]` | 200, 422 |
| POST | `/api/v1/game/scores` | `ScoreCreateRequest` | `ScoreRecord` | 200, 403, 422 |
| DELETE | `/api/v1/game/scores` | none (admin clearance) | empty | 204, 401 |

### `GET /api/v1/health`

Liveness and configuration status. Use it as the container health check.

`HealthResponse`:

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | `"healthy"` | Constant |
| `service` | string | `PROJECT_NAME` |
| `version` | string | `VERSION` |
| `model_loaded` | boolean | The ML filter's baseline classifier is loaded |
| `agent_tiers` | `("budget" \| "standard")[]` | Agent tiers running a live model; the others use the offline stand-in |
| `storage_backend` | `"supabase"` \| `"memory"` | Active store (spec 0046); `memory` only in tests |

```json
{"status":"healthy","service":"AI S.H.I.E.L.D.","version":"0.2.0","model_loaded":true,"agent_tiers":["budget","standard"],"storage_backend":"supabase"}
```

### Clearance

`POST /api/v1/clearance` is behind BotID in production. Failed attempts count per address and per email (`CLEARANCE_MAX_ATTEMPTS` in `CLEARANCE_WINDOW_MINUTES`, `429`); a valid sign-in resets both. The `shield_session` cookie is `SameSite=Strict`. Grants, refusals and `DELETE /api/v1/game/scores` write audit records to the `shield_api.audit` logger, with a hash of the email and never the password (spec 0054).

An admin is a Supabase Auth user whose `app_metadata.role` is `"admin"`
(`mise run admin:create <email>`). The email and password are sent once; the
gateway signs in with Supabase Auth, checks the role, signs that Supabase
session out, and answers with an opaque session cookie. Only the token's
SHA-256 hash is stored (`audit.clearance_sessions`).

| Route | Body | Response |
| --- | --- | --- |
| `POST /api/v1/clearance` | `{"email": string, "password": string}` (password 1 to 512 characters) | `200 ClearanceStatus` and `Set-Cookie`; `401` with one generic `detail` for a wrong password, an unknown email, a non-admin account or no Supabase; `429` with `Retry-After` after `CLEARANCE_MAX_ATTEMPTS` failures in `CLEARANCE_WINDOW_MINUTES` |
| `GET /api/v1/clearance` | none | `200 ClearanceStatus` |
| `DELETE /api/v1/clearance` | none | `204`; deletes the session and expires the cookie. Safe without a session |

`ClearanceStatus`: `granted` (boolean), `expires_at` (datetime or `null`).

Cookie: `shield_session`, `HttpOnly`, `SameSite=Lax`, `Path=/api/v1`,
`Max-Age` = `SESSION_TTL_MINUTES`, plus `Secure` when `SESSION_COOKIE_SECURE`.

Admin clearance, which unlocks the `/_console` data and `DELETE /api/v1/game/scores`:

| Request | Clearance |
| --- | --- |
| Live session cookie | `GRANTED` |
| A failed `POST /clearance` from the same address within the window, and no live session | `DENIED` |
| Anything else (no, unknown, expired or revoked cookie; session-store error) | `NONE` |

The client address is the socket peer; forwarded headers are ignored unless
uvicorn runs with `--proxy-headers`.

## `ai-shield` player authentication endpoints

### `GET /api/v1/auth/session`

Returns `PlayerSessionStatus` (`authenticated`, `is_anonymous`, `tier`, `email`, `player_name`, `ai_nodes_allowed`, `can_record_scores`, `daily_wave_limit`, `wave_runs_used`, `daily_test_limit`, `test_runs_used`).

### `POST /api/v1/auth/anonymous`

Creates a free anonymous player session (`is_anonymous=true`, `tier="anonymous"`, `ai_nodes_allowed=false`, `can_record_scores=false`), setting the `HttpOnly` cookie `shield_player_session`. It makes no Supabase call. Rate-limited to `30/hour` per client IP in production (`429` with `Retry-After`) and protected by BotID (`403`).

### `POST /api/v1/auth/register`

Registers an account (`email`, `password` of 8 to 512 characters with at least one number, one lowercase letter, and one uppercase letter, optional `player_name`) on the `free` tier (`ai_nodes_allowed=true`, `can_record_scores=true`, `daily_wave_limit=5`, `daily_test_limit=20`). `email` must look like `name@domain.tld`, or the request is `422` (specs 0027, 0036).

- **With Supabase** (spec 0027): calls Supabase Auth `sign_up` with a link back to `WEB_BASE_URL/auth/confirmed` and answers `202 {"status": "confirmation_sent"}` with **no cookie**. The answer is identical for new, unconfirmed and existing emails, and when Supabase fails. If the project has **Confirm email** off, the player is signed in instead (`200` and the cookie).
- **Without Supabase** (local development): signs the player in at once (`200`, cookie) and returns `409 Conflict` for a taken email.

### `POST /api/v1/auth/login`

Signs in an existing player (`email`, `password` of 8 to 512 characters) and sets `shield_player_session`. In production, failed sign-ins count per email (`10/15m`), and a valid sign-in resets that count (spec 0054). Returns `422` on invalid email or short password and `401 Unauthorized` on invalid credentials.

With Supabase, the password is checked by Supabase Auth (a local `password_hash` from before spec 0027 is never used).

If the request carries a live anonymous `shield_player_session`, the gateway moves that session's scores from `game.anonymous_scores` to `game.scores` and the leaderboard. The account keeps the better score for each level. Then the gateway deletes the anonymous rows, revokes the old token and sets a new cookie. An expired cookie, or the cookie of a signed-in player, moves nothing. A storage error does not stop the sign-in. `POST /api/v1/auth/confirm` and `POST /api/v1/auth/register` do the same when they sign the player in (spec 0052). `403` means the email is not confirmed yet (`"Confirm your email before signing in."`); `503` means Supabase Auth failed for another reason. The first sign-in creates the player's free profile from `user_metadata.player_name`; later sign-ins keep its name and tier.

### `POST /api/v1/auth/resend-confirmation`

Sends the confirmation email again (Supabase `resend`, `type="signup"`). Always `202 {"status": "confirmation_sent"}`, whatever the email; without Supabase it sends nothing.

### `POST /api/v1/auth/recover`

Triggers a password recovery email via Supabase `reset_password_for_email` and returns `PlayerRecoverResponse` (`{"status": "ok"}`).

### Account settings (`/api/v1/auth/account/*`, spec 0025)

All of these need a signed-in, non-anonymous player session (`403` otherwise). All except
`PATCH …/profile` need the `current_password` (`401` when wrong; after 5 wrong passwords for one account in
`CLEARANCE_WINDOW_MINUTES`, `429`). Unknown fields are `422`. Store or Supabase
failures are `503` with a generic message.

- `POST …/password` `{current_password, new_password}` (8 to 512 chars with at least one number, one lowercase letter, and one uppercase letter, different from the current one): sets the new password and ends every session of the account. The caller gets a new `shield_player_session` cookie and keeps its trained model (spec 0054).
- `POST …/email` `{new_email, current_password}`: `409` if the address has an account, `422` if unchanged. Starts Supabase Auth's confirm-change email flow (`update_user`) and returns `202 {"status": "confirmation_sent"}`; existing scores, saved boards, usage and sessions stay under the current email until the player confirms the new address and signs in with it (spec 0042). Requires **Confirm email** and **Secure email change** enabled in production Supabase Auth.
- `PATCH …/profile` `{player_name}` (1 to 64 characters, no control or format characters; no password): changes the display name on the account, its sessions, its scores and the leaderboard (spec 0048). At most 5 changes in 15 minutes in production.
- `POST …/reset-progress` `{current_password}`: deletes the account's scores and saved boards; returns `{"scores_removed": n, "boards_removed": m}`.
- `DELETE /api/v1/auth/account` `{current_password, confirm: "DELETE"}`: deletes saved boards, scores, sessions, trained models and the account (and the Supabase user), sets `players.purchases.email` to `NULL`, deletes the account's `players.daily_usage` rows older than 30 UTC days (spec 0058), keeps the recent usage counts, and clears the cookie. `204`.
- `GET …/export` (spec 0058): `AccountExportResponse` with `exported_at`, `account` (`email`, `player_name`, `tier`, `paid_until`, `created_at`), `saved_boards` (`level_id`, `updated_at`, `save`), `scores` (the player's own `game.scores` rows) and `purchases` (`id`, `amount_cents`, `currency`, `status`, `starts_at`, `ends_at`, `created_at`, `settled_at`). Never a token hash, a password or another player's row. `403` without a signed-in player; `Cache-Control: private, no-store`; in production at most 5 exports per account in 15 minutes (`429` with `Retry-After`).

Supabase Auth checks the current password, and the changes go through its admin API (spec 0027).

Scores recorded for a signed-in player store the player's email, so each account
keeps its own best score per level. `GET /api/v1/game/scores` never returns it.

### `POST /api/v1/auth/upgrade`

Upgrades a signed-in `free` player to `tier="paid"` (`daily_wave_limit=50`, `daily_test_limit=1000`) when `ALLOW_SELF_UPGRADE=true`. Returns `403` (`"Paid plans are not available yet."`) when disabled, or for anonymous/unauthenticated callers. A successful upgrade sets a new `shield_player_session` cookie and revokes the old token (spec 0054).

### `POST /api/v1/auth/logout`

Revokes the active player session and clears `shield_player_session` (`204 No Content`).

## `ai-shield` game endpoints

### Billing (`/api/v1/billing/*`, spec 0049)

- `POST …/checkout`: creates a Stripe Checkout Session for one 30-day pass (USD 5, one payment) and returns `{"url"}`. The page expires after 30 minutes and is reused while it is open. `409` when a payment is processing, or when there is nothing to buy. At most 10 in 15 minutes for one account in production.
- `POST …/sync` `{cancel}`: reads the open checkout from Stripe and grants a paid pass, so a missed webhook or a lost connection is repaired. `cancel: true` expires an unpaid session. Returns `{state, session}`.
- `POST …/webhook`: verifies `Stripe-Signature` on the raw body. A paid event adds 30 days to `paid_until` once. A full refund or a chargeback removes the unused days once; a failed refund or a won chargeback gives them back. A payment for a deleted account is refunded. `503` makes Stripe send the event again.
- The session status has `paid_until`. The tier is `paid` while it is in the future, or when the account has a manual grant.

### `GET /api/v1/game/levels`

The response is the same for every caller, so it has `Cache-Control: public, s-maxage=300, stale-while-revalidate=86400` and the CDN can answer it. The gateway builds the catalogue once per process.

A run, save or score request for a removed level (`medium-8`, `medium-9`, `medium-10`, `hard-8`) gets `404 This level was removed from the campaign.` Migration `20261126180000_campaign_v2_levels.sql` deletes their saved boards and scores (API-LADDER-001).

Returns `GameCatalogResponse`:

- `levels`: 19 campaign definitions (`easy-1`..`easy-5`, `medium-1`..`medium-7`, `hard-1`..`hard-7`, spec 0051), each with `id`, `new_idea`, `briefing` (`family` and `text` examples), `version`, `attack_floor`, `benign_floor`, `title`, `difficulty` (`"Easy" | "Medium" | "Hard"`), `order`, `tier` (`"free" | "paid"`), `tags`, `summary`, `protected_asset`, `max_latency_ms`, `max_cost_usd`, `constraints` (`LevelConstraintsSchema` or `null`), `follow_up` (`FollowUpChallengeSchema` or `null`), `messages` (each with `id`, `is_attack` and `category`; `text` is empty, `expected_tool` is `null` and `forbidden_tools` is empty, because wave prompts stay on the server, spec 0050), `agent` (`objective`, `tools` with `name`/`description`/`allowed`/`dual_use`, `token_budget`; `null` on `easy-1..5`, which run no model), `agent_tier` (`null`, `standard` or `budget`) and `final_node_label` (`Help Desk` on `easy-1..5`, else `Protected Agent`). The per-run canary is never included.
- `checks`: available tool node definitions (`text_cleanup`, `word_filter`, `length_limit`, `secret_scan`, `ml_classifier`, `jev`, `safety_check`, `llm_review`) with handles, typical latency, and cost. `jev`, `safety_check`, and `llm_review` support the Tool Policy extension (`tool_policy_enabled`, `block_tools`).
- `billing_enabled`: boolean, true when Stripe checkout is configured (spec 0049).
- `self_upgrade_enabled`: boolean matching `ALLOW_SELF_UPGRADE`.

### `POST /api/v1/game/train`

Requires a signed-in non-anonymous player session (`403` `"Sign in to train the ML filter."` otherwise) and valid `MODEL_SIGNING_KEY` (`503` in production if unset). Custom mode (`level_id: "custom"`) requires a `paid` plan (`403`, max body 1.25 MB / 2,000 rows); campaign mode caps bodies at 128 KB / 200 rows, or at the level's `max_training_rows` when it is lower (`easy-4`: 40 rows). A request over the level limit gets `422` that names the limit and uses no training run (API-LADDER-003). Validates strict `text,label` CSV or typed `dataset` rows (labels `0`, `1`, `safe`, `attack`; max 500 cleaned chars), reserves a daily quota slot atomically (`3` free, `200` paid), fits once with `max_features=5000` in a persistent warm child worker process (cold-start import completes before the 10 s fit timeout begins; fits exceeding 10 s kill the worker and return `503`, counted toward the daily quota), HMAC-signs and stores one model per session (max 1 MB, 30 min idle TTL; `413` and `422` errors do not count), discards raw rows, and returns `GameTrainResponse` (`model_id`, `algorithm`, `sample_count`, `accuracy`, `expires_at`) without echoing `dataset` (spec 0045).

### `DELETE /api/v1/game/models` and `POST /api/v1/game/models/purge`

Idempotent `204` endpoints that purge the current session's server-held ML model on route leave or `pagehide` beacon (spec 0045).

### `POST /api/v1/game/run`

Evaluates a player's `BoardGraphSchema` against the selected level wave using server-side master API keys. Each run is a scored attempt, and the best attempt is kept (spec 0050). A campaign level takes no `custom_message`: the request is `422`. Only the custom sandbox (`level_id: "custom"`) accepts one:

- The board needs one `incoming` and one `assistant` (AI Agent) node. A board that still contains a `blocked` node returns `422` with `Remove the Blocked node; unreached prompts are blocked automatically.` The AI Agent's `config.rules` accepts up to 5 rules of at most 200 characters.
- Pro-tier campaign levels (`level.tier == "paid"`, i.e., `easy-4..5`, `medium-3..7`, `hard-1..7`) require a signed-in player with `tier == "paid"`; anonymous or free callers get `403 Upgrade to Pro to play this level.` before any quota is charged.
- Hard levels enforce `validate_board_for_level` (`max_nodes`, `allowed_kinds`, `disallowed_kinds`) before charging quota, returning `422` on topology constraint violations.
- `easy-1..5` are classification only unless wired with a hosted model check (`safety_check`, `llm_review`, or `jev`): a prompt that reaches the final node (`Help Desk`) is let through, no agent model runs, and the response says `agent_mode: "none"`. Model-free Easy runs stay sessionless and uncounted; any run against a level with an agent or a hosted check requires a valid session cookie (`401 "Start a session to play this level."`) and counts toward daily quotas. Boards are capped at 60 nodes and 200 edges (`422`), and a custom sandbox `custom_message` at 1,000 characters (`422`). A board holds at most 8 check nodes, and at most 2 of them are model nodes (`jev`, `safety_check`, `llm_review`); a larger board is `422`.
- **Custom sandbox** (`level_id: "custom"`, paid players only, spec 0022): check nodes (`safety_check`, `llm_review`) run on the player's BYOK model, never server keys (spec 0042).
- On `medium-1..10` and `hard-1..8`, prompts that reach the AI Agent run against the model for the level's tier (`GAME_MODEL_STANDARD` for `Medium`, `GAME_MODEL_BUDGET` for `Hard`) with the level objective and the player's rules. With no model for the tier, a deterministic stand-in runs and the response says `agent_mode: "simulated"`.
- Each trace includes `agent` (`reply`, `tool_calls`, `refused`, `verdict`, `input_tokens`, `output_tokens`, `estimated_tokens`, `latency_ms`, `cost_usd`) when the prompt reached the agent. `score` includes `protection_points`, `helpfulness_points`, `tool_points`, `token_points`, `speed_points`, `cost_points`, `leak_penalty`, `total_tokens`, `constraint_violations`, `follow_up_passed`, and `follow_up_feedback`.
- Anonymous callers are rejected with `403 Forbidden` if the board includes AI agent nodes (`jev`, `safety_check`, or `llm_review`), and their scores are not recorded on the leaderboard.
- A campaign response holds no prompt text, agent reply or free-text detail: each trace has `text: ""`, each hop has `detail: ""`, and `agent.reply` is `""`. Each trace has `category` (the prompt family), and a `jev` or `ml_classifier` hop has `score` (API-FAIR-001).
- `score` has the spec 0050 parts: `cleared_points`, `accuracy_points`, `speed_points`, `cost_points`, `simplicity_points`, `quality`, `list_latency_ms` and `list_cost_usd`. A run that does not clear scores at most 4,999; a cleared run scores 5,000 to 10,000. Speed and cost use the catalogue list prices, so the same board gets the same score. `avg_latency_ms` is the list latency.
- `stop` is `null`, or a `RunStopSchema` (`reason` `time_limit` or `budget`, `prompt_index`, `node_id`, `limit`, `used`, `path` of `node_id`, `kind`, `latency_ms` and `cost_usd`) when a prompt went over the level's latency limit or the wave went over its cost budget. Then the run stops at that prompt and scores 0.
- The agent result of a prompt is stored and used again for the same board on the same level. Each level has a fixed canary that is never shown.
- Daily limits per UTC day: anonymous 1 wave, `free` 5 waves, `paid` 50 waves; training `free` 3 and `paid` 20 (`429 Too Many Requests` when exceeded). A run that a limit stopped counts. Each player also has a daily provider budget: $0.02 for anonymous and `free`, $0.10 for `paid`. At the budget, a run that uses a model returns `429` before any model call, and the detail gives the UTC reset time (spec 0050). The quota slot is reserved atomically before the run (`players.reserve_daily_usage`) and released (`players.release_daily_usage`) if board execution fails with `422`, `502`, or `503`. Model-free `Easy` runs and tests never count toward the quota.
- If the chat model fails, the response is `503 Service Unavailable`, no run is charged and nothing is recorded.
- **Custom sandbox** (`level_id: "custom"`, paid players only, spec 0022): the body adds `custom` with `agent` (`objective` up to 1,000 characters, up to 10 `tools` with `name`/`description`/`allowed`), `dataset` (1 to 50 rows of `text`, `label` `normal`/`attack`, optional `expected_tool`) and `model` (`provider`, one of `openai`, `anthropic`, `google`, `groq`, `deepseek`, `qwen`, `moonshot`; `model`, matching `[A-Za-z0-9._:/-]`, up to 100 characters; `api_key`, up to 200 characters). There is no URL field, and unknown fields return `422`. Non-paid callers get `403`. The run uses the player's key for that one request, returns `agent_mode: "custom"`, never counts toward the quota and is never recorded. A provider that rejects the key returns `502` with `The model provider rejected the API key.`; any other provider failure returns `502` with `The model provider did not respond.`
- Completed level wave runs by logged-in players record the score (`won`, `mastered`) on the leaderboard under their account `player_name` when `agent_mode` is `live` or `none`. Simulated runs are never recorded.
- A run by an anonymous session with a valid cookie records the same score in `game.anonymous_scores`, keyed by the SHA-256 hash of the token, for 7 days. It keeps the best run for each level and never goes on the leaderboard. Sign-in moves it to the account (spec 0052).

### `GET /api/v1/game/saves/{level_id}` and `PUT /api/v1/game/saves/{level_id}`

Saved boards (specs 0023 and 0039), one per signed-in player and level (`easy-1..5`, `medium-1..10`, `hard-1..8`, `custom`), stored in `game.saved_boards`.

- `PUT` takes `SavedBoardRequest`: `board` (`BoardGraphSchema`), `positions` (node id to `{x, y}`) and, for `custom` only, `custom` (`agent`, `dataset`, `provider`, `model`). There is no key field, and unknown fields return `422`, so an `api_key` can never be stored. A save replaces the previous one. Limits: 60 nodes, 200 edges (`422`) and 256 KB (`413`). The board is not run through `validate_board`, so unfinished boards can be saved.
- `GET` returns `SavedBoardResponse` (the save plus `level_id` and `updated_at`), or `404` when nothing is saved.
- Anonymous callers get `403 Sign in to save your board.`; Pro-tier levels (`easy-4..5`, `medium-3..7`, `hard-1..7`) and `custom` saves need a paid plan (`403`).

### `GET /api/v1/game/leaderboard`

Each gateway process reuses a board read for 5 seconds (the CDN already caches for 10), and drops it when a score is recorded in that process.

Returns `DifficultyLeaderboardEntry[]` for `difficulty` (`"Easy" | "Medium" | "Hard"`, default `"Easy"`) and `limit` (1–100, default 20), served from Redis sorted sets (`lb:v<ver>:z:<board>`) with `Cache-Control: public, s-maxage=10, stale-while-revalidate=30` and boundary tie-group reads capped at 250 entries, aggregating each player's current-version (`SCORE_VERSION = 4`) best won scores across all levels in that difficulty (`total_score`, `levels_solved`, `levels_total`, `levels_mastered`, `avg_latency_ms`, `total_cost_usd`, `reached_at`), ordered by `total_score DESC`, `levels_mastered DESC`, `reached_at ASC` (the earlier date wins), `player_name ASC` (API-FAIR-005). Only **won** runs count toward `total_score`, and players whose total is `0` are omitted. A lost run never replaces a stored won run for the same level, and a won run always replaces a stored lost run (API-CAMP-004, spec 0044).

### `GET /api/v1/game/leaderboard/me`

Requires a signed-in (non-anonymous) player session (`403` otherwise). Returns `LeaderboardRankResponse` (`difficulty`, `rank`, `total_score`) with `Cache-Control: private, no-store` (spec 0044). Ties on the primary score are scanned in bounded 250-member pages up to 1,000 members with member-keyed record pairing and self-healing cache invalidation on incomplete entries.

### `GET /api/v1/game/progress`

Returns `PlayerProgressResponse` (`levels` keyed by all 19 `LevelId` slugs with `best_score`, `medal`, `won`, `mastered`, and `difficulties` keyed by `Easy`/`Medium`/`Hard` with `total_score`, `levels_cleared`, `levels_total`, `levels_mastered`). An anonymous session with a valid cookie receives its pending scores from `game.anonymous_scores` (spec 0052). Unauthenticated callers receive all-zero / unsolved entries (`200 OK`).

### `GET /api/v1/game/scores`

Returns `ScoreRecord[]` ordered by `total_score DESC` (tie-broken by `avg_latency_ms ASC` and `total_cost_usd ASC`), with optional `level_id` and `limit` query parameters. Only rows with the current `score_version` (`4`) are listed. Migration `20261126120000_score_version_4.sql` deletes all rows with `score_version < 4` (API-FAIR-006); earlier legacy rows were purged by migration `20261119104405_campaign_levels_and_mastery.sql`.

### `DELETE /api/v1/game/scores`

Requires an active admin clearance session (`Cookie: shield_session=...`). Clears the scoreboard (`204 No Content`), returning `401 Unauthorized` when clearance is not granted.
