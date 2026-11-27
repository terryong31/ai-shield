-- Spec 0056: daily usage reservations count up to the limit and never below zero.
begin;
select plan(6);

select is(
  (select reserved from players.reserve_daily_usage('pgtap@example.invalid', '2026-11-27', 'wave', 0)),
  false, 'a limit of 0 reserves nothing'
);
select is(
  (select wave_runs from players.reserve_daily_usage('pgtap@example.invalid', '2026-11-27', 'wave', 2)),
  1, 'the first reservation inserts the row'
);
select is(
  (select wave_runs from players.reserve_daily_usage('pgtap@example.invalid', '2026-11-27', 'wave', 2)),
  2, 'the second reservation reaches the limit'
);
select is(
  (select reserved from players.reserve_daily_usage('pgtap@example.invalid', '2026-11-27', 'wave', 2)),
  false, 'the limit is not passed'
);
select throws_ok(
  $$select * from players.reserve_daily_usage('pgtap@example.invalid', '2026-11-27', 'chat', 5)$$,
  'P0001', null, 'an unknown kind raises'
);
select is(
  (select train_runs from players.release_daily_usage('pgtap@example.invalid', '2026-11-27', 'train')),
  0, 'release never goes below zero'
);

select * from finish();
rollback;
