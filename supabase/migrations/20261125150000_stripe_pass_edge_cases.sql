-- Spec 0049: one open checkout for each player, exact refund windows, chargebacks.

alter table players.purchases drop constraint if exists purchases_status_check;
alter table players.purchases add constraint purchases_status_check
  check (status in ('pending', 'expired', 'paid', 'refunded', 'disputed'));

alter table players.purchases add column if not exists checkout_session_id text;
alter table players.purchases add column if not exists starts_at timestamptz;
alter table players.purchases add column if not exists ends_at timestamptz;
alter table players.purchases add column if not exists removed interval not null default interval '0';

-- Local databases can hold pending rows from the first version of this feature.
update players.purchases set status = 'expired' where status = 'pending';

create unique index if not exists purchases_one_pending_idx
  on players.purchases (email, livemode) where status = 'pending';
create unique index if not exists purchases_payment_intent_idx
  on players.purchases (payment_intent) where payment_intent is not null;

drop function if exists players.fulfil_purchase(uuid, text, integer);
drop function if exists players.refund_purchase(uuid, integer);

create or replace function players.fulfil_purchase(
  p_id uuid,
  p_payment_intent text,
  p_amount integer,
  p_currency text,
  p_days integer
)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_purchase players.purchases%rowtype;
  v_until timestamptz;
  v_start timestamptz;
  v_end timestamptz;
begin
  select * into v_purchase from players.purchases as p where p.id = p_id for update;
  if not found then
    return 'unknown';
  end if;
  if v_purchase.status not in ('pending', 'expired') then
    return 'duplicate';
  end if;
  if v_purchase.amount_cents <> p_amount or v_purchase.currency <> p_currency then
    return 'mismatch';
  end if;
  if v_purchase.email is null then
    return 'orphaned';
  end if;

  select a.paid_until into v_until
  from players.accounts as a
  where a.email = v_purchase.email
  for update;
  if not found then
    return 'no_account';
  end if;

  v_start := greatest(now(), coalesce(v_until, now()));
  v_end := v_start + make_interval(days => p_days);
  update players.accounts as a set paid_until = v_end where a.email = v_purchase.email;
  update players.purchases as p
  set status = 'paid',
      payment_intent = p_payment_intent,
      starts_at = v_start,
      ends_at = v_end,
      settled_at = now()
  where p.id = p_id;
  return 'fulfilled';
end;
$$;

-- Removes the unused days of a purchase once and moves later passes forward.
create or replace function players.revoke_purchase(
  p_id uuid,
  p_payment_intent text,
  p_status text
)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_purchase players.purchases%rowtype;
  v_removed interval := interval '0';
begin
  if p_status not in ('refunded', 'disputed') then
    raise exception 'Unsupported purchase status: %', p_status;
  end if;
  select * into v_purchase
  from players.purchases as p
  where p.id = p_id or (p_id is null and p.payment_intent = p_payment_intent)
  for update;
  if not found then
    return 'unknown';
  end if;
  if v_purchase.status in ('refunded', 'disputed') then
    if p_status = 'refunded' then
      update players.purchases as p set status = 'refunded' where p.id = v_purchase.id;
    end if;
    return 'duplicate';
  end if;

  if v_purchase.status = 'paid' and v_purchase.email is not null then
    v_removed := greatest(
      interval '0', v_purchase.ends_at - greatest(now(), v_purchase.starts_at)
    );
    update players.accounts as a
    set paid_until = a.paid_until - v_removed
    where a.email = v_purchase.email;
    if not found then
      return 'no_account';
    end if;
    update players.purchases as p
    set starts_at = p.starts_at - v_removed, ends_at = p.ends_at - v_removed
    where p.email = v_purchase.email
      and p.status = 'paid'
      and p.id <> v_purchase.id
      and p.starts_at >= v_purchase.ends_at;
  end if;

  update players.purchases as p
  set status = p_status, removed = v_removed, settled_at = now()
  where p.id = v_purchase.id;
  return 'revoked';
end;
$$;

-- Gives removed days back when a refund fails or a chargeback is won.
create or replace function players.restore_purchase(
  p_payment_intent text,
  p_status text
)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_purchase players.purchases%rowtype;
  v_until timestamptz;
  v_start timestamptz;
begin
  select * into v_purchase
  from players.purchases as p
  where p.payment_intent = p_payment_intent
  for update;
  if not found then
    return 'unknown';
  end if;
  if v_purchase.status <> p_status then
    return 'duplicate';
  end if;
  if v_purchase.email is null then
    return 'orphaned';
  end if;

  select a.paid_until into v_until
  from players.accounts as a
  where a.email = v_purchase.email
  for update;
  if not found then
    return 'no_account';
  end if;

  v_start := greatest(now(), coalesce(v_until, now()));
  update players.accounts as a
  set paid_until = v_start + v_purchase.removed
  where a.email = v_purchase.email;
  update players.purchases as p
  set status = 'paid',
      starts_at = v_start,
      ends_at = v_start + v_purchase.removed,
      removed = interval '0',
      settled_at = now()
  where p.id = v_purchase.id;
  return 'restored';
end;
$$;

revoke all on function players.fulfil_purchase(uuid, text, integer, text, integer)
  from public, anon, authenticated;
revoke all on function players.revoke_purchase(uuid, text, text)
  from public, anon, authenticated;
revoke all on function players.restore_purchase(text, text)
  from public, anon, authenticated;

grant execute on function players.fulfil_purchase(uuid, text, integer, text, integer)
  to service_role;
grant execute on function players.revoke_purchase(uuid, text, text) to service_role;
grant execute on function players.restore_purchase(text, text) to service_role;
