-- Spec 0042 / 0045 hotfix: atomic daily usage reservation and failure refund.
-- Eliminates check-then-upsert races on daily wave, test, and train limits.

create or replace function players.reserve_daily_usage(
  p_email text,
  p_usage_date date,
  p_kind text,
  p_limit integer
)
returns table (
  reserved boolean,
  wave_runs integer,
  test_runs integer,
  train_runs integer
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_wave integer;
  v_test integer;
  v_train integer;
begin
  if p_kind not in ('wave', 'test', 'train') then
    raise exception 'Unsupported daily usage kind: %', p_kind;
  end if;

  if p_limit <= 0 then
    select d.wave_runs, d.test_runs, d.train_runs
    into v_wave, v_test, v_train
    from players.daily_usage as d
    where d.email = p_email
      and d.usage_date = p_usage_date;

    return query select
      false,
      coalesce(v_wave, 0),
      coalesce(v_test, 0),
      coalesce(v_train, 0);
    return;
  end if;

  insert into players.daily_usage as d (
    email,
    usage_date,
    wave_runs,
    test_runs,
    train_runs
  )
  values (
    p_email,
    p_usage_date,
    case when p_kind = 'wave' and p_limit > 0 then 1 else 0 end,
    case when p_kind = 'test' and p_limit > 0 then 1 else 0 end,
    case when p_kind = 'train' and p_limit > 0 then 1 else 0 end
  )
  on conflict (email, usage_date) do update
    set
      wave_runs = case
        when p_kind = 'wave' and d.wave_runs < p_limit then d.wave_runs + 1
        else d.wave_runs
      end,
      test_runs = case
        when p_kind = 'test' and d.test_runs < p_limit then d.test_runs + 1
        else d.test_runs
      end,
      train_runs = case
        when p_kind = 'train' and d.train_runs < p_limit then d.train_runs + 1
        else d.train_runs
      end
    where
      (p_kind = 'wave' and d.wave_runs < p_limit)
      or (p_kind = 'test' and d.test_runs < p_limit)
      or (p_kind = 'train' and d.train_runs < p_limit)
  returning d.wave_runs, d.test_runs, d.train_runs
  into v_wave, v_test, v_train;

  if found and p_limit > 0 then
    return query select true, v_wave, v_test, v_train;
    return;
  end if;

  select d.wave_runs, d.test_runs, d.train_runs
  into v_wave, v_test, v_train
  from players.daily_usage as d
  where d.email = p_email
    and d.usage_date = p_usage_date;

  return query select
    false,
    coalesce(v_wave, 0),
    coalesce(v_test, 0),
    coalesce(v_train, 0);
end;
$$;

create or replace function players.release_daily_usage(
  p_email text,
  p_usage_date date,
  p_kind text
)
returns table (
  wave_runs integer,
  test_runs integer,
  train_runs integer
)
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if p_kind not in ('wave', 'test', 'train') then
    raise exception 'Unsupported daily usage kind: %', p_kind;
  end if;

  return query
  update players.daily_usage as d
  set
    wave_runs = case when p_kind = 'wave' then greatest(0, d.wave_runs - 1) else d.wave_runs end,
    test_runs = case when p_kind = 'test' then greatest(0, d.test_runs - 1) else d.test_runs end,
    train_runs = case when p_kind = 'train' then greatest(0, d.train_runs - 1) else d.train_runs end
  where d.email = p_email
    and d.usage_date = p_usage_date
  returning d.wave_runs, d.test_runs, d.train_runs;
end;
$$;

revoke all on function players.reserve_daily_usage(text, date, text, integer)
  from public, anon, authenticated;
revoke all on function players.release_daily_usage(text, date, text)
  from public, anon, authenticated;

grant execute on function players.reserve_daily_usage(text, date, text, integer)
  to service_role;
grant execute on function players.release_daily_usage(text, date, text)
  to service_role;
