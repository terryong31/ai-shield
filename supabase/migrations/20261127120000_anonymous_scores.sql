-- Spec 0052: server-evaluated scores of anonymous players, kept until they sign in.
-- Rows are keyed by the SHA-256 hash of the HttpOnly session token, never the raw token.

create table if not exists game.anonymous_scores (
  session_token_hash text             not null,
  level_id           text             not null,
  score_version      integer          not null,
  player_name        text             not null default 'Player',
  total_score        integer          not null,
  medal              text             not null,
  attacks_blocked    integer          not null,
  attacks_total      integer          not null,
  false_alarms       integer          not null,
  avg_latency_ms     double precision not null,
  total_cost_usd     double precision not null,
  board_json         jsonb            not null,
  won                boolean          not null default false,
  mastered           boolean          not null default false,
  created_at         timestamptz      not null default now(),
  expires_at         timestamptz      not null,
  primary key (session_token_hash, level_id, score_version)
);

create index if not exists anonymous_scores_expires_at_idx on game.anonymous_scores (expires_at);

comment on table game.anonymous_scores is 'Anonymous players'' best runs per level. Moved to game.scores on sign-in, deleted after 7 days.';

alter table game.anonymous_scores enable row level security;
revoke all on table game.anonymous_scores from public, anon, authenticated;
grant all on table game.anonymous_scores to service_role;

create index if not exists daily_usage_anonymous_date_idx
  on players.daily_usage (usage_date)
  where email like 'anon:%';
