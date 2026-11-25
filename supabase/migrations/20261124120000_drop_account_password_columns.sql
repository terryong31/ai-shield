-- Spec 0046: drop legacy local password columns now that Supabase Auth is the only identity provider.

alter table players.accounts drop column if exists password_hash;
alter table players.accounts drop column if exists salt;

comment on table players.accounts is
  'Player profiles (name, tier). Passwords live in Supabase Auth (spec 0046).';
