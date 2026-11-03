-- Milestone 7b: dashboard support.
-- Club crests and competition emblems as published by the data provider (URLs, not files).
alter table teams add column if not exists crest_url text;
alter table competitions add column if not exists emblem_url text;

-- Historical ("backfilled") runs: forecasts recomputed later with an earlier data cutoff,
-- so the dashboard can show how a forecast would have evolved matchday by matchday.
-- They use only data before their cutoff, but they were not made at that time; the flag
-- keeps that distinction visible.
alter table model_runs add column if not exists is_backfill boolean not null default false;

-- "Latest forecast" means the latest DATA CUTOFF (a backfill run is stored after the
-- current run but describes an earlier point in the season).
create index if not exists model_runs_season_cutoff_idx
    on model_runs (season_id, data_cutoff desc, run_at desc);
