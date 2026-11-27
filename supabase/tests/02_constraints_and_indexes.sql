-- Spec 0056: check constraints and the unique indexes of purchases.
begin;
select plan(7);

select has_index('players', 'purchases', 'purchases_one_pending_idx', 'one pending purchase index');
select has_index('players', 'purchases', 'purchases_payment_intent_idx', 'payment intent index');

insert into players.accounts (email, player_name, tier) values ('pgtap@example.invalid', 'pgTAP', 'free');

select throws_ok(
  $$insert into players.accounts (email, player_name, tier) values ('pgtap2@example.invalid', 'x', 'gold')$$,
  '23514', null, 'accounts.tier is checked'
);
select throws_ok(
  $$insert into players.purchases (id, email, amount_cents, currency, livemode, status)
    values (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', false, 'lost')$$,
  '23514', null, 'purchases.status is checked'
);

insert into players.purchases (id, email, amount_cents, currency, livemode, status)
values (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', false, 'pending'),
       (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', true, 'pending'),
       (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', false, 'expired'),
       (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', false, 'expired');

select throws_ok(
  $$insert into players.purchases (id, email, amount_cents, currency, livemode, status)
    values (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', false, 'pending')$$,
  '23505', null, 'a second pending purchase for one email and mode is refused'
);

insert into players.purchases (id, email, amount_cents, currency, livemode, status, payment_intent)
values (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', false, 'paid', 'pi_pgtap');

select throws_ok(
  $$insert into players.purchases (id, email, amount_cents, currency, livemode, status, payment_intent)
    values (gen_random_uuid(), 'pgtap@example.invalid', 500, 'usd', false, 'paid', 'pi_pgtap')$$,
  '23505', null, 'a payment intent is used once'
);

select is(
  (select count(*)::int from players.purchases where email = 'pgtap@example.invalid' and payment_intent is null),
  4,
  'many rows may have no payment intent'
);

select * from finish();
rollback;
