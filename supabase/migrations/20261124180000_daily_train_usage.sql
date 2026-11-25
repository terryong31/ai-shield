-- Spec 0045: daily ML training run quota counter.
alter table players.daily_usage
  add column if not exists train_runs integer not null default 0;
