-- Spec 0025: scores belong to an account (by email), not to a display name.
-- Rows recorded before this have no email and are left as they are.

alter table game.scores add column if not exists email text;

create index if not exists scores_owner_idx
  on game.scores (email, level_id, score_version);

comment on column game.scores.email is
  'Owning player account; never returned by GET /game/scores. Null for scores recorded before spec 0025.';
