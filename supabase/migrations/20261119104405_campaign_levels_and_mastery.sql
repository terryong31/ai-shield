-- Spec 0039: campaign levels, win/mastery flags, and legacy pre-campaign purge.

alter table game.scores add column if not exists won boolean not null default false;
alter table game.scores add column if not exists mastered boolean not null default false;

create index if not exists scores_version_level_idx
  on game.scores (score_version, level_id);

delete from game.scores where score_version < 3 or level_id in ('easy', 'medium', 'hard');
delete from game.saved_boards where level_id in ('easy', 'medium', 'hard');
