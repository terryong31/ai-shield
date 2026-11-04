-- Audit log of every prompt screened by the gateway (apps/api).
-- Written and read only by the gateway with a server-side key; the browser
-- never talks to this table (ADR 0004). Keep columns in sync with
-- apps/api/src/shield_api/services/audit.py (spec 0009, API-STORE-006).

create table public.requests (
  id          uuid        primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  query       text        not null,
  action      text        not null check (action in ('ALLOWED', 'BLOCKED')),
  reason      text        not null default '',
  layer       text        not null,
  metadata    jsonb       not null default '{}'::jsonb,
  reviewed    boolean     not null default false,
  human_label smallint    check (human_label in (0, 1))
);

comment on table public.requests is 'AI S.H.I.E.L.D. audit log: one row per screened prompt.';
comment on column public.requests.layer is 'Deciding layer: LAYER_1_ML, LAYER_2_DUAL_AGENT or SYSTEM.';
comment on column public.requests.human_label is 'Reviewer label: 1 = malicious, 0 = safe, null = not reviewed.';

-- Dashboard queries: newest first, and counts by action.
create index requests_created_at_idx on public.requests (created_at desc);
create index requests_action_idx on public.requests (action);

-- Deny by default. No policies for anon/authenticated: only the service role
-- (which bypasses RLS) can read or write.
alter table public.requests enable row level security;
revoke all on table public.requests from anon, authenticated;
