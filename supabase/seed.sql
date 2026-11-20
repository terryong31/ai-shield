-- Demo data for local development. Runs after migrations on `supabase start`
-- (first run) and on every `supabase db reset`. Never runs against production.
--
-- The game needs no seed rows: players, scores and saved boards are created by
-- playing. The request audit log this file used to seed was removed in spec 0026.
select 1;
