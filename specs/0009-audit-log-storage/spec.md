# 0009 — Audit log storage backends

- **Status:** Implemented
- **Area:** API
- **Created:** 2026-09-23
- **Related:** spec 0007, [persist the audit log](../../docs/how-to/persist-the-audit-log.md), `supabase/migrations/`

## Problem

Without Supabase credentials the gateway kept the audit log in memory, so every
restart erased the history, dashboard stats and reviewer labels. There was also
no versioned database schema: the Supabase `requests` table existed only as SQL
pasted from a how-to page, so there was nothing to migrate or reproduce.

## Goals

- Durable local persistence with zero setup: SQLite whenever Supabase is not configured.
- A versioned Supabase project (`supabase/`) with migrations, seed data and
  config, so the schema can be applied locally and pushed to any project.
- Every backend honours the same `AuditLog` behaviour.
- Operators can see which backend is active.

## Non-goals

- Migrating existing SQLite rows into Supabase.
- Running SQLite in multi-replica deployments (a single-writer file store).

## Behaviour

Backend selection at startup (first match wins):

| Condition | Backend | `audit_backend` |
| --- | --- | --- |
| `SUPABASE_URL` **and** `SUPABASE_KEY` set | Supabase `public.requests` | `supabase` |
| otherwise | SQLite file at `SQLITE_PATH` (default `var/shield.db`) | `sqlite` |

`InMemoryAuditLog` remains as a test double and reports `memory`.

The SQLite table mirrors the columns of the Supabase migration
(`id, created_at, query, action, reason, layer, metadata, reviewed, human_label`).
`metadata` is stored as JSON text.

## Acceptance criteria

- **API-STORE-001**: Given no Supabase URL or key, when the container is built, then the audit log is a `SqliteAuditLog` at `SQLITE_PATH`, creating parent directories and the schema if missing.
- **API-STORE-002**: Given a record written through one `SqliteAuditLog`, when a new instance opens the same file, then the record is returned by `recent()` (it survives a restart).
- **API-STORE-003**: Every backend (memory, SQLite, Supabase) returns records newest first and respects `limit`, computes `stats()` as in API-STATS-001, and `review()` sets `reviewed`, `human_label` and the matching `action`; reviewing an unknown id is a no-op.
- **API-STORE-004**: Given both `SUPABASE_URL` and `SUPABASE_KEY`, when the container is built, then the audit log is a `SupabaseAuditLog`; if only one is set, SQLite is used.
- **API-STORE-005**: `GET /api/v1/health` reports `audit_backend` as `sqlite`, `supabase` or `memory`.
- **API-STORE-006**: The SQLite schema has exactly the columns created for `public.requests` by the Supabase migrations.

## Security & privacy considerations

- The SQLite file contains raw prompts. It lives under `var/` (git-ignored) or
  a Docker volume; treat it as sensitive.
- The Supabase migration enables RLS with no policies for `anon`/`authenticated`,
  so only the server-side key used by the gateway can read or write.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: API-STORE-001, API-STORE-002, API-STORE-003, API-STORE-004, API-STORE-005, API-STORE-006
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 17 passing test(s)
- Gate: `mise run check` passed
