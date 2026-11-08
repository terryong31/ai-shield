-- Domain-scoped schemas (spec 0024). No application table stays in `public`:
--   audit   - gateway screening audit log and admin clearance sessions
--   game    - leaderboard scores and saved boards
--   players - player accounts, sessions and daily run quotas
-- Only the gateway's service_role key reads or writes these (ADR 0004). Keep the
-- columns in sync with the SQLite stores in apps/api/src/shield_api/services/
-- (API-SCHEMA-006).

create schema if not exists audit;
create schema if not exists game;
create schema if not exists players;

-- audit -----------------------------------------------------------------------

alter table if exists public.requests set schema audit;

create table if not exists audit.clearance_sessions (
  token_hash text        primary key,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index if not exists clearance_sessions_expires_at_idx
  on audit.clearance_sessions (expires_at);

comment on table audit.clearance_sessions is 'Admin console clearance sessions: SHA-256 token hashes only.';

-- game ------------------------------------------------------------------------

create table if not exists game.scores (
  id              uuid             primary key default gen_random_uuid(),
  created_at      timestamptz      not null default now(),
  player_name     text             not null,
  level_id        text             not null,
  total_score     integer          not null,
  medal           text             not null check (medal in ('none', 'bronze', 'silver', 'gold')),
  attacks_blocked integer          not null,
  attacks_total   integer          not null,
  false_alarms    integer          not null,
  avg_latency_ms  double precision not null,
  total_cost_usd  double precision not null,
  board_json      jsonb            not null,
  score_version   integer          not null default 1
);

create index if not exists scores_rank_idx
  on game.scores (level_id, score_version, total_score desc, avg_latency_ms asc, total_cost_usd asc);

comment on table game.scores is 'Leaderboard: best score per player, level and score_version.';

create table if not exists game.saved_boards (
  email      text        not null,
  level_id   text        not null,
  save_json  jsonb       not null,
  updated_at timestamptz not null default now(),
  primary key (email, level_id)
);

comment on table game.saved_boards is 'One saved board per player and level (spec 0023). Never holds API keys.';

-- players ---------------------------------------------------------------------

create table if not exists players.accounts (
  email         text        primary key,
  password_hash text        not null,
  salt          text        not null,
  player_name   text        not null,
  tier          text        not null default 'free' check (tier in ('free', 'paid')),
  created_at    timestamptz not null default now()
);

create table if not exists players.sessions (
  token_hash   text        primary key,
  email        text,
  is_anonymous boolean     not null,
  player_name  text        not null,
  tier         text        not null,
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null
);

create table if not exists players.daily_usage (
  email      text    not null,
  usage_date date    not null,
  wave_runs  integer not null default 0,
  test_runs  integer not null default 0,
  primary key (email, usage_date)
);

comment on table players.accounts is 'Player accounts: PBKDF2-HMAC-SHA256 password hashes with per-account salts.';
comment on table players.sessions is 'Player and anonymous sessions: SHA-256 token hashes only.';
comment on table players.daily_usage is 'Wave and test runs per player (or hashed anonymous session) per UTC day.';

-- Deny by default ---------------------------------------------------------------
-- RLS on with no policies, nothing granted to anon or authenticated: only the
-- service role (which bypasses RLS) can resolve these schemas.

alter table audit.requests enable row level security;
alter table audit.clearance_sessions enable row level security;
alter table game.scores enable row level security;
alter table game.saved_boards enable row level security;
alter table players.accounts enable row level security;
alter table players.sessions enable row level security;
alter table players.daily_usage enable row level security;

revoke all on table audit.requests from public, anon, authenticated;
revoke all on table audit.clearance_sessions from public, anon, authenticated;
revoke all on table game.scores from public, anon, authenticated;
revoke all on table game.saved_boards from public, anon, authenticated;
revoke all on table players.accounts from public, anon, authenticated;
revoke all on table players.sessions from public, anon, authenticated;
revoke all on table players.daily_usage from public, anon, authenticated;

revoke all on schema audit from public, anon, authenticated;
revoke all on schema game from public, anon, authenticated;
revoke all on schema players from public, anon, authenticated;

grant usage on schema audit to service_role;
grant usage on schema game to service_role;
grant usage on schema players to service_role;

grant all on all tables in schema audit to service_role;
grant all on all tables in schema game to service_role;
grant all on all tables in schema players to service_role;

alter default privileges in schema audit grant all on tables to service_role;
alter default privileges in schema game grant all on tables to service_role;
alter default privileges in schema players grant all on tables to service_role;
