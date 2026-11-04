# 0007 — Gateway HTTP API

- **Status:** Implemented
- **Area:** API
- **Created:** 2026-09-23
- **Related:** [ADR 0002](../../docs/explanation/decisions/0002-engine-gateway-split.md), [ADR 0004](../../docs/explanation/decisions/0004-frontend-talks-only-to-gateway.md), [ADR 0005](../../docs/explanation/decisions/0005-ndjson-event-stream.md), [HTTP reference](../../docs/reference/http-api.md)

## Problem

The demo needs an HTTP surface over the engine. The web client also read the
audit log straight from Supabase with a public anon key, which coupled the
frontend to the database schema and exposed the table to every browser.

## Goals

- A thin gateway: map HTTP ↔ engine, run the demo assistant and tools, own
  persistence. No detection logic lives here.
- The web client needs nothing but this API.
- A committed OpenAPI contract the client is generated from.

## Behaviour

All routes live under `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | liveness + model status |
| POST | `/predict` | Layer 1 signal only |
| POST | `/screen` | full engine decision, no assistant |
| POST | `/chat` | full demo: screen → assistant → tools, streamed as NDJSON |
| POST | `/feedback` | record a reviewer label |
| GET | `/requests` | audit log, newest first |
| GET | `/stats` | aggregate counts |

Demo modes map to engine config: `shield` → defaults, `guardrail` →
`always_adjudicate`, `chaos` → `skip_classifier`.

Passphrase mapping: absent → `NONE`; equal to `SECURE_PASSPHRASE` (constant-
time compare) → `GRANTED`; otherwise `DENIED`.

## Acceptance criteria

- **API-HEALTH-001**: `GET /api/v1/health` returns 200 with `status="healthy"` and `model_loaded=true` when the classifier is available.
- **API-PRED-001**: `POST /api/v1/predict` returns the Layer 1 verdict and score for a prompt; a body without `message` returns 422.
- **API-SCREEN-001**: `POST /api/v1/screen` returns the engine decision (`verdict`, `policy`, `blocked`, `layer`, `reason`) without invoking the demo assistant.
- **API-CHAT-001**: `POST /api/v1/chat` responds `application/x-ndjson`, one JSON object per line; the first event is `START` and an allowed request ends with `FINAL_RESPONSE`.
- **API-CHAT-002**: Given a prompt the engine blocks, the stream contains `BLOCK` then `STAGE_CHANGE(final)`, never `FINAL_RESPONSE`, the assistant is not invoked, and an audit record with `action=BLOCKED` and the decision layer is stored.
- ~~API-CHAT-003~~ Retired 2026-09-24: superseded by API-CLEAR-004 and API-CLEAR-011 (spec 0012).
- **API-CHAT-004**: Mode `guardrail` sets `always_adjudicate` and mode `chaos` sets `skip_classifier` for that request only.
- **API-CHAT-005**: The assistant receives exactly the tools allowed by the decision policy, and emitted `TOOL_START`/`TOOL_END` events are relayed in the stream.
- **API-CHAT-006**: Given an unexpected server error mid-stream, the stream emits an `ERROR` event with a generic message that contains no exception text.
- **API-FEED-001**: `POST /api/v1/feedback` teaches the classifier the label and, when `request_id` is given, marks that audit record reviewed with the new action.
- **API-LOG-001**: `GET /api/v1/requests` returns audit records newest first; `limit` defaults to 30 and must be within 1–200 (else 422).
- **API-STATS-001**: `GET /api/v1/stats` returns `total`, `blocked`, `allowed` and `block_rate` (percent, one decimal, 0 when empty).
- **API-CONTRACT-001**: The OpenAPI document advertises only `/api/v1` routes and is identical to the committed `contracts/shield-api.openapi.json`.
- **API-TOOLS-001**: In the demo tool catalogue, every tool that deletes, drops, exports or executes arbitrary queries is rated `HIGH` or `CRITICAL`.

## Security & privacy considerations

- Supabase credentials leave the browser entirely; only the gateway holds them.
- The passphrase is a demo stand-in for RBAC. It is compared in constant time
  and never logged.
- Stream errors are generic to avoid leaking internals.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: API-HEALTH-001, API-PRED-001, API-SCREEN-001, API-CHAT-001, API-CHAT-002, API-CHAT-003, API-CHAT-004, API-CHAT-005, API-CHAT-006, API-FEED-001, API-LOG-001, API-STATS-001, API-CONTRACT-001, API-TOOLS-001
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 25 passing test(s)
- Gate: `mise run check` passed
