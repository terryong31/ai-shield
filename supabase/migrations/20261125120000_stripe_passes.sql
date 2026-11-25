-- Spec 0049: 30-day passes bought with Stripe Checkout.

alter table players.accounts add column if not exists paid_until timestamptz;

create table if not exists players.purchases (
  id             uuid        primary key,
  email          text,
  amount_cents   integer     not null,
  currency       text        not null,
  livemode       boolean     not null,
  status         text        not null default 'pending' check (status in ('pending', 'paid', 'refunded')),
  payment_intent text,
  created_at     timestamptz not null default now(),
  settled_at     timestamptz
);

create index if not exists purchases_email_idx on players.purchases (email);

comment on table players.purchases is 'Stripe pass purchases. The email is null after the account is deleted.';

alter table players.purchases enable row level security;
revoke all on table players.purchases from public, anon, authenticated;
grant all on table players.purchases to service_role;

-- Grants the days of a pending purchase once. The row lock makes concurrent
-- deliveries of one event safe.
create or replace function players.fulfil_purchase(
  p_id uuid,
  p_payment_intent text,
  p_days integer
)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_email text;
  v_status text;
begin
  select p.email, p.status into v_email, v_status
  from players.purchases as p
  where p.id = p_id
  for update;

  if not found then
    return 'unknown';
  end if;
  if v_status <> 'pending' then
    return 'duplicate';
  end if;

  update players.accounts as a
  set paid_until = greatest(now(), coalesce(a.paid_until, now())) + make_interval(days => p_days)
  where a.email = v_email;
  if not found then
    return 'no_account';
  end if;

  update players.purchases as p
  set status = 'paid', payment_intent = p_payment_intent, settled_at = now()
  where p.id = p_id;
  return 'fulfilled';
end;
$$;

create or replace function players.refund_purchase(
  p_id uuid,
  p_days integer
)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_email text;
  v_status text;
begin
  select p.email, p.status into v_email, v_status
  from players.purchases as p
  where p.id = p_id
  for update;

  if not found then
    return 'unknown';
  end if;
  if v_status = 'refunded' then
    return 'duplicate';
  end if;

  if v_status = 'paid' and v_email is not null then
    update players.accounts as a
    set paid_until = a.paid_until - make_interval(days => p_days)
    where a.email = v_email;
    if not found then
      return 'no_account';
    end if;
  end if;

  update players.purchases as p
  set status = 'refunded', settled_at = now()
  where p.id = p_id;
  return 'refunded';
end;
$$;

revoke all on function players.fulfil_purchase(uuid, text, integer)
  from public, anon, authenticated;
revoke all on function players.refund_purchase(uuid, integer)
  from public, anon, authenticated;

grant execute on function players.fulfil_purchase(uuid, text, integer) to service_role;
grant execute on function players.refund_purchase(uuid, integer) to service_role;
