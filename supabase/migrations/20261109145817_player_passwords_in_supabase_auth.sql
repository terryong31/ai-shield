-- Spec 0027: Supabase Auth owns player passwords and email confirmation.
-- Profiles created after this have no local password hash; older rows keep
-- theirs, but it is never checked when Supabase is configured.

alter table players.accounts alter column password_hash drop not null;
alter table players.accounts alter column salt drop not null;

comment on table players.accounts is
  'Player profiles (name, tier). Passwords live in Supabase Auth; password_hash/salt are legacy (spec 0027).';
