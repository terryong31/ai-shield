-- The hosted project had schema-level grants but no table-level grants for
-- service_role on the domain schemas (PostgREST 42501 "permission denied for
-- table accounts"). Re-apply them idempotently. anon and authenticated still
-- get nothing (ADR 0004). 20261109134541 was pushed empty by mistake.

grant usage on schema audit, game, players to service_role;

grant all on all tables in schema audit to service_role;
grant all on all tables in schema game to service_role;
grant all on all tables in schema players to service_role;

grant all on all sequences in schema audit to service_role;
grant all on all sequences in schema game to service_role;
grant all on all sequences in schema players to service_role;

alter default privileges in schema audit grant all on tables to service_role;
alter default privileges in schema game grant all on tables to service_role;
alter default privileges in schema players grant all on tables to service_role;
