# 0004. The frontend talks only to the gateway

- **Status:** Accepted
- **Date:** 2026-09-23

## Context

In the previous Next.js application the browser read the audit log straight
from Supabase. Client components created a Supabase client from
`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` and queried and
subscribed to the `requests` table. This meant:

- the anon key and table were exposed to every visitor, so the table's safety
  depended entirely on Row Level Security policies that the application did not
  manage;
- the frontend was coupled to the database schema, so a column change could
  break the UI silently;
- there was no single place to add authentication, filtering or redaction.

The frontend was also being rewritten in Nuxt, which was the moment to fix the
boundary.

## Decision

The web client (`apps/web`) communicates only with the gateway API:

- All backend access goes through `useShieldApi()`; there is no Supabase or
  other database client in the web app, and no secret in `runtimeConfig.public`.
  The only public setting is the gateway URL (`NUXT_PUBLIC_API_BASE_URL`).
- The gateway owns persistence behind an `AuditLog` protocol (SQLite or
  Supabase) and exposes `GET /requests`, `GET /stats` and `POST /feedback`.
- The gateway uses a server-side Supabase key (`SUPABASE_KEY`); the table can
  run with RLS enabled and no policies for anonymous roles.
- The web client's types are generated from the committed OpenAPI contract
  (`contracts/shield-api.openapi.json` → `app/types/api.gen.ts`), and CI fails
  if the contract or generated types drift from the code.

## Consequences

- No database credentials reach the browser. The previous direct anon-key
  access is removed.
- Schema changes are contained in the gateway; contract changes are explicit,
  generated and type-checked.
- Authentication, rate limiting and redaction can be added in one place (they
  are not yet implemented; see the threat model).
- Real-time updates that the old app got from Supabase subscriptions are gone;
  the dashboard refreshes on demand.
- The gateway becomes a required component even for read-only dashboards.
