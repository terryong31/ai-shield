-- Spec 0056: every application table has RLS and no grants to client roles.
begin;
select plan(5);

select is(
  (select count(*)::int from pg_tables where schemaname = 'public'),
  0,
  'no application tables in public'
);

select is(
  (select count(*)::int
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where c.relkind = 'r' and n.nspname in ('audit', 'game', 'players') and not c.relrowsecurity),
  0,
  'every table in audit, game and players has row level security'
);

select is(
  (select count(*)::int from information_schema.role_table_grants
   where table_schema in ('audit', 'game', 'players')
     and grantee in ('PUBLIC', 'anon', 'authenticated')),
  0,
  'anon, authenticated and PUBLIC hold no table privileges'
);

select is(
  (select count(*)::int
   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'players'
     and (has_function_privilege('anon', p.oid, 'execute')
       or has_function_privilege('authenticated', p.oid, 'execute'))),
  0,
  'client roles cannot execute any players function'
);

select ok(
  has_table_privilege('service_role', 'players.accounts', 'select, insert, update, delete')
  and has_function_privilege('service_role', 'players.reserve_daily_usage(text, date, text, integer)', 'execute'),
  'service_role can use the tables and the functions'
);

select * from finish();
rollback;
