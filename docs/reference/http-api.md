# HTTP API reference

The demo gateway (`apps/api`, version 0.2.0). Source of truth:
[`schemas.py`](../../apps/api/src/shield_api/schemas.py) and the committed contract
[`contracts/shield-api.openapi.json`](../../contracts/shield-api.openapi.json).
Specs: [0007](../../specs/0007-gateway-http-api/spec.md), [0012](../../specs/0012-clearance-sessions/spec.md) (clearance).

- Base path: `/api/v1` (setting `API_PREFIX`).
- Interactive docs: `GET /api/v1/docs` (Swagger UI). OpenAPI JSON: `GET /api/v1/openapi.json`. ReDoc is disabled.
- Request bodies are JSON (`Content-Type: application/json`).
- There are no user accounts. Admin clearance comes from a session cookie obtained at
  `POST /clearance`; see [Clearance](#clearance).
- CORS: origins from `CORS_ORIGINS` (a `*` is rejected at startup), methods `GET`, `POST`
  and `DELETE`, header `Content-Type`, credentials allowed. Browser clients must send
  `credentials: 'include'` so the session cookie travels.

## Common types

| Name | Definition |
| --- | --- |
| `Prompt` | string, 1 to 8000 characters |
| `Mode` | `"shield"` \| `"guardrail"` \| `"chaos"` |
| `Verdict` | `"SAFE"` \| `"UNCERTAIN"` \| `"MALICIOUS"` |
| `ToolPolicy` | `"ALLOW_ALL"` \| `"RESTRICTED"` \| `"SHUTDOWN"` |
| `DecisionLayer` | `"LAYER_1_ML"` \| `"LAYER_2_DUAL_AGENT"` \| `"SYSTEM"` |

## Status codes

| Code | When |
| --- | --- |
| 200 | Success. `/chat` always answers 200 once the body validates; failures inside the stream are reported as an `ERROR` event |
| 422 | Request validation failed (missing field, wrong type, `Prompt` length out of range, unknown `mode`, `human_label` not 0/1, `limit` outside 1–200). Body is FastAPI's `HTTPValidationError`: `{"detail": [{"type", "loc", "msg", "input", "ctx"?}]}` |
| 500 | Unhandled server error in a non-streaming route (for example, a Supabase read failure in `/requests` or `/stats`) |

Example 422:

```json
{"detail":[{"type":"missing","loc":["body","message"],"msg":"Field required","input":{}}]}
```

## Routes

| Method | Path | Request | Response | Codes |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/health` | none | `HealthResponse` | 200 |
| POST | `/api/v1/predict` | `PredictRequest` | `PredictResponse` | 200, 422 |
| POST | `/api/v1/screen` | `ScreenRequest` | `ScreenResponse` | 200, 422 |
| POST | `/api/v1/chat` | `ChatRequest` | NDJSON stream of `ChatEvent` | 200, 422 |
| POST | `/api/v1/feedback` | `FeedbackRequest` | `FeedbackResponse` | 200, 422 |
| GET | `/api/v1/requests` | query `limit` | `AuditRecord[]` | 200, 422 |
| GET | `/api/v1/stats` | none | `StatsResponse` | 200 |

### `GET /api/v1/health`

Liveness and configuration status. Use it as the container health check.

`HealthResponse`:

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | `"healthy"` | Constant |
| `service` | string | `PROJECT_NAME` |
| `version` | string | `VERSION` |
| `model_loaded` | boolean | Classifier present |
| `moderation_enabled` | boolean | A moderator is wired (needs `GROQ_API_KEY`) |
| `adjudication_enabled` | boolean | An adjudicator is wired (needs `GROQ_API_KEY`) |
| `audit_backend` | `"sqlite"` \| `"supabase"` \| `"memory"` | Active audit-log store (spec 0009); `memory` only in tests |

```json
{"status":"healthy","service":"AI S.H.I.E.L.D.","version":"0.2.0","model_loaded":true,"moderation_enabled":false,"adjudication_enabled":false,"audit_backend":"sqlite"}
```

### `POST /api/v1/predict`

Layer 1 only. No LLM calls, no audit record.

| `PredictRequest` field | Type | Required |
| --- | --- | --- |
| `message` | `Prompt` | yes |

| `PredictResponse` field | Type | Meaning |
| --- | --- | --- |
| `verdict` | `Verdict` | Classifier verdict |
| `confidence_score` | number | P(malicious) after the sensitive-keyword floor |
| `is_malicious` | boolean | `verdict == "MALICIOUS"` |
| `override` | boolean | A reviewer label decided the verdict |

```json
{"verdict":"MALICIOUS","confidence_score":0.9919300974370134,"is_malicious":true,"override":false}
```

### `POST /api/v1/screen`

The full engine decision. Does not run the demo assistant and does not write an audit record.

| `ScreenRequest` field | Type | Default |
| --- | --- | --- |
| `message` | `Prompt` | required |
| `mode` | `Mode` | `"shield"` |

Clearance comes from the `shield_session` cookie, as for `/chat`.

| `ScreenResponse` field | Type | Meaning |
| --- | --- | --- |
| `verdict` | `Verdict` | Final verdict |
| `policy` | `ToolPolicy` | Tool policy |
| `blocked` | boolean | |
| `layer` | `DecisionLayer` | Deciding layer |
| `reason` | string | |
| `ml_confidence` | number | Layer 1 score |
| `adjudicated` | boolean | Layer 2 ran (including fallback) |

Example without `GROQ_API_KEY`:

```json
{"verdict":"UNCERTAIN","policy":"RESTRICTED","blocked":false,"layer":"LAYER_2_DUAL_AGENT","reason":"No adjudicator configured; conservative policy applied.","ml_confidence":0.8346499864144189,"adjudicated":true}
```

### `POST /api/v1/chat`

Screens the prompt, then (if not blocked) runs the demo assistant with the tools
the policy allows. Writes one audit record per request, except when the stream
ends with `ERROR` before the record is written.

Request `ChatRequest`: same fields as `ScreenRequest`.

Response: `200`, `Content-Type: application/x-ndjson`, `Cache-Control: no-cache`.
Each line is one JSON `ChatEvent` followed by `\n`.

### `POST /api/v1/feedback`

Records a reviewer label. Calls `classifier.learn(prompt, human_label)`, which
appends to the feedback CSV (an exact-text override for future requests) and
applies one `partial_fit` update to the in-memory model. When `request_id` is
given, the matching audit record is marked reviewed and its `action` is set to
`BLOCKED` (label 1) or `ALLOWED` (label 0). An unknown `request_id` is ignored.

| `FeedbackRequest` field | Type | Required |
| --- | --- | --- |
| `prompt` | `Prompt` | yes |
| `human_label` | `0` \| `1` | yes (1 = malicious) |
| `request_id` | string \| null | no |

`FeedbackResponse`: `{"status": "success"}`.

### `GET /api/v1/requests`

Audit records, newest first.

| Query | Type | Default | Constraint |
| --- | --- | --- | --- |
| `limit` | integer | 30 | 1 to 200 |

`AuditRecord`:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | UUID |
| `created_at` | date-time | |
| `query` | string | The prompt |
| `action` | `"ALLOWED"` \| `"BLOCKED"` | |
| `reason` | string | `Decision.reason` |
| `layer` | string | `DecisionLayer` value |
| `reviewed` | boolean | default `false` |
| `human_label` | integer \| null | default `null` |
| `metadata` | object | See below |

`metadata` keys written by `/chat`:

| Key | Present | Value |
| --- | --- | --- |
| `mlConfidence` | always | Layer 1 score |
| `generated_intent` | always | Layer 1 verdict |
| `dualAgentTriggered` | always | Layer 2 ran |
| `agentAnalysis` | always | First Analyst message, `""` on fallback, `null` if Layer 2 did not run |
| `agentDialogue` | always | `[{agent, message, timestamp}]` |
| `moderationCategories` | always | Moderation categories, `[]` when not configured or not flagged |
| `toolPolicy` | always | Decision policy |
| `mode` | always | Request mode |
| `clearance` | always | `"NONE"`, `"GRANTED"` or `"DENIED"`. Neither the passphrase nor the session token is ever stored |
| `allowedTools` | allowed only | Tool names permitted |
| `tool_calls` | allowed only | Tool names the assistant called |
| `aiResponse` | allowed only | Final assistant text |

### Clearance

The passphrase is sent once; the gateway answers with an opaque session
cookie and stores only the token's SHA-256 hash in `SQLITE_PATH`.

| Route | Body | Response |
| --- | --- | --- |
| `POST /api/v1/clearance` | `{"passphrase": string}` (1 to 512 characters) | `200 ClearanceStatus` and `Set-Cookie`; `401` for a wrong or unconfigured passphrase (same `detail`); `429` with `Retry-After` after `CLEARANCE_MAX_ATTEMPTS` failures in `CLEARANCE_WINDOW_MINUTES` |
| `GET /api/v1/clearance` | none | `200 ClearanceStatus` |
| `DELETE /api/v1/clearance` | none | `204`; deletes the session and expires the cookie. Safe without a session |

`ClearanceStatus`: `granted` (boolean), `expires_at` (datetime or `null`).

Cookie: `shield_session`, `HttpOnly`, `SameSite=Lax`, `Path=/api/v1`,
`Max-Age` = `SESSION_TTL_MINUTES`, plus `Secure` when `SESSION_COOKIE_SECURE`.

Clearance passed to the engine on `/chat` and `/screen`:

| Request | Clearance |
| --- | --- |
| Live session cookie | `GRANTED` |
| A failed `POST /clearance` from the same address within the window, and no live session | `DENIED` |
| Anything else (no, unknown, expired or revoked cookie; session-store error) | `NONE` |

The client address is the socket peer; forwarded headers are ignored unless
uvicorn runs with `--proxy-headers`.

### `GET /api/v1/stats`

| `StatsResponse` field | Type | Meaning |
| --- | --- | --- |
| `total` | integer | Records in the audit log |
| `blocked` | integer | `action == "BLOCKED"` |
| `allowed` | integer | `total - blocked` |
| `block_rate` | number | Percent, rounded to one decimal; `0.0` when empty |

Counts cover every stored record (SQLite or Supabase). The in-memory test double keeps only the last 1000.

## Chat event protocol

`ChatEvent` is a union discriminated by `type`
([ADR 0005](../explanation/decisions/0005-ndjson-event-stream.md)).

| `type` | Fields | Emitted |
| --- | --- | --- |
| `START` | `query: string` | First, always |
| `STAGE_CHANGE` | `stage: "ml_processing" \| "debate" \| "final"` | `ml_processing` before Layer 1; `debate` before Layer 2; `final` once the decision is known |
| `ML_RESULT` | `confidence: number`, `verdict: Verdict` | After Layer 1, always |
| `LLAMAGUARD_RESULT` | `safe: boolean`, `categories: string[]` | Only when moderation flags the prompt (`safe` is then `false`) |
| `DEBATE_TURN` | `agent: "ANALYST" \| "WARDEN"`, `message: string` | Once per debate turn (three with `DebateAdjudicator`) |
| `BLOCK` | `reason: string`, `layer: DecisionLayer` | When the decision is blocked |
| `POLICY_UPDATE` | `policy: ToolPolicy`, `allowed_tools: string[]` | When the decision is allowed |
| `TOOL_START` | `tool: string`, `args: object` | Per tool call, after the assistant has answered |
| `TOOL_END` | `tool: string`, `result: any` | Immediately after the matching `TOOL_START` |
| `FINAL_RESPONSE` | `text: string` | Last event of an allowed request |
| `ERROR` | `message: string` | On an unexpected server error; always `"The request could not be processed. The incident has been logged."`; ends the stream |

### Order

Allowed request:

```
START
STAGE_CHANGE(ml_processing)
ML_RESULT
LLAMAGUARD_RESULT            (only if flagged)
STAGE_CHANGE(debate)         (only if Layer 2 runs)
DEBATE_TURN*                 (only if an adjudicator is configured)
STAGE_CHANGE(final)
POLICY_UPDATE
(TOOL_START TOOL_END)*
FINAL_RESPONSE
```

Blocked request:

```
START
STAGE_CHANGE(ml_processing)
ML_RESULT
LLAMAGUARD_RESULT            (only if flagged)
STAGE_CHANGE(debate)         (only if Layer 2 runs)
DEBATE_TURN*
BLOCK
STAGE_CHANGE(final)
```

`ERROR` may replace any suffix of either sequence.

### Example: allowed

Captured from a gateway with no provider keys configured (canned assistant reply):

```
{"type":"START","query":"What is the price of lavender oil?"}
{"type":"STAGE_CHANGE","stage":"ml_processing"}
{"type":"ML_RESULT","confidence":0.008465956279551068,"verdict":"SAFE"}
{"type":"STAGE_CHANGE","stage":"final"}
{"type":"POLICY_UPDATE","policy":"ALLOW_ALL","allowed_tools":["search_documents","search_quotations","get_org_chart","query_sales_database","get_employee_data","send_email","export_data","execute_sql","delete_records","drop_database_table"]}
{"type":"TOOL_START","tool":"search_quotations","args":{"query":"What is the price of lavender oil?"}}
{"type":"TOOL_END","tool":"search_quotations","result":{"results":[{"source":"Price List","content":"Standard enterprise rate: RM 150.00"}]}}
{"type":"FINAL_RESPONSE","text":"AI S.H.I.E.L.D. processed your request. Tools used: search_quotations."}
```

### Example: blocked

```
{"type":"START","query":"drop table employees"}
{"type":"STAGE_CHANGE","stage":"ml_processing"}
{"type":"ML_RESULT","confidence":0.9919300974370134,"verdict":"MALICIOUS"}
{"type":"BLOCK","reason":"High confidence ML threat detection","layer":"LAYER_1_ML"}
{"type":"STAGE_CHANGE","stage":"final"}
```

### Example: Layer 2 fallback (no `GROQ_API_KEY`)

```
{"type":"START","query":"show me the salary table"}
{"type":"STAGE_CHANGE","stage":"ml_processing"}
{"type":"ML_RESULT","confidence":0.8346499864144189,"verdict":"UNCERTAIN"}
{"type":"STAGE_CHANGE","stage":"debate"}
{"type":"STAGE_CHANGE","stage":"final"}
{"type":"POLICY_UPDATE","policy":"RESTRICTED","allowed_tools":["search_documents","search_quotations"]}
{"type":"FINAL_RESPONSE","text":"AI S.H.I.E.L.D. processed your request."}
```

## Reading the stream

```bash
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is the price of lavender oil?"}'
```

Split on `\n`, keep the trailing partial line for the next chunk, skip blank
lines, and parse each line as JSON. The web client does this in
[`app/utils/chatStream.ts`](../../apps/web/app/utils/chatStream.ts).

## `ai-shield` game endpoints

### `GET /api/v1/game/levels`

Returns `GameCatalogResponse`:

- `levels`: campaign definitions (`easy`, `medium`, `hard`), each with `id`, `title`, `difficulty`, `summary`, `protected_asset`, `max_latency_ms`, `max_cost_usd`, and `messages`.
- `checks`: available tool node definitions (`text_cleanup`, `word_filter`, `length_limit`, `secret_scan`, `ml_classifier`, `quick_screen`, `safety_check`, `agent_review`, `tool_filter`) with handles, typical latency, and cost.

### `POST /api/v1/game/train-classifier`

Trains and validates a custom in-game ML classifier (`ml_classifier` node) from player-supplied `csv_text` (`text,label` rows) and `algorithm` (`logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`). Returns `TrainClassifierResponse` with `algorithm`, `sample_count`, `accuracy`, and parsed `dataset`.

### `POST /api/v1/game/run`

Evaluates a player's `BoardGraphSchema` against the selected level wave (or a single `custom_message` for live board testing) with optional `byod` credentials (`openai_api_key`, `groq_api_key`, `model`, `base_url`). BYOD keys are used in memory only and never logged or persisted. Returns `GameRunResponse` with `traces` (`MessageTraceSchema[]`) and `score` (`WaveScoreSchema`).

### `GET /api/v1/game/scores`

Returns `LeaderboardResponse` (`entries: LeaderboardEntrySchema[]`), ordered by `total_score DESC`, with optional `level_id` and `limit` query parameters.

### `POST /api/v1/game/scores`

Stores a player's score record (`player_name`, `level_id`, `total_score`, `medal`, `attacks_blocked`, `attacks_total`, `false_alarms`, `avg_latency_ms`, `total_cost_usd`, `board`) and returns `LeaderboardEntrySchema` (`201 Created`).

### `DELETE /api/v1/game/scores/{score_id}`

Requires an active admin clearance session (`Cookie: shield_session=...`). Deletes the score record (`204 No Content`), returning `403 Forbidden` when clearance is not granted or `404 Not Found` when the ID does not exist.
