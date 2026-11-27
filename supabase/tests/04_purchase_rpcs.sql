-- Spec 0056: fulfil, revoke and restore move the exact intervals.
begin;
select plan(8);

insert into players.accounts (email, player_name, tier) values ('pgtap@example.invalid', 'pgTAP', 'free');
insert into players.purchases (id, email, amount_cents, currency, livemode, status)
values ('00000000-0000-4000-8000-000000000001', 'pgtap@example.invalid', 500, 'usd', false, 'pending'),
       ('00000000-0000-4000-8000-000000000002', 'pgtap@example.invalid', 500, 'usd', false, 'expired'),
       ('00000000-0000-4000-8000-000000000003', null, 500, 'usd', false, 'expired');

select is(players.fulfil_purchase(gen_random_uuid(), 'pi_x', 500, 'usd', 30), 'unknown', 'unknown purchase');
select is(players.fulfil_purchase('00000000-0000-4000-8000-000000000003', 'pi_o', 500, 'usd', 30), 'orphaned', 'orphaned purchase');
select is(players.fulfil_purchase('00000000-0000-4000-8000-000000000001', 'pi_m', 499, 'usd', 30), 'mismatch', 'amount mismatch');
select is(players.fulfil_purchase('00000000-0000-4000-8000-000000000001', 'pi_1', 500, 'usd', 30), 'fulfilled', 'first pass');
select is(players.fulfil_purchase('00000000-0000-4000-8000-000000000001', 'pi_1', 500, 'usd', 30), 'duplicate', 'paid once');
select is(players.fulfil_purchase('00000000-0000-4000-8000-000000000002', 'pi_2', 500, 'usd', 30), 'fulfilled', 'stacked pass');

select is(
  players.revoke_purchase('00000000-0000-4000-8000-000000000001', null, 'refunded'),
  'revoked', 'a refund removes the unused days'
);
select is(
  (select ends_at - starts_at from players.purchases where id = '00000000-0000-4000-8000-000000000002'),
  interval '30 days', 'the later pass moves forward and keeps its length'
);

select * from finish();
rollback;
