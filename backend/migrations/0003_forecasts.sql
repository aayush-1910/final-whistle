-- ============================================================================
-- 0003 — Model runs and their outputs (Milestone 4)
--
-- A model run records everything needed to reproduce a forecast: model name
-- and parameters, data cutoff, seed, simulation count, code version.
-- Outputs reference the run and never modify source data.
-- ============================================================================

create table model_runs (
    id               bigint generated always as identity primary key,
    model_name       text not null,                 -- e.g. 'poisson-montecarlo'
    model_version    text not null,                 -- e.g. '0.1.0'
    params           jsonb not null,                -- full model + rules parameters
    competition_id   smallint not null references competitions (id),
    season_id        integer not null references seasons (id),
    data_cutoff      timestamptz not null,          -- only matches before this were used
    run_at           timestamptz not null default now(),
    seed             bigint not null,
    simulation_count integer not null check (simulation_count > 0),
    code_version     text,                          -- git commit of the code that ran
    status           text not null default 'completed'
                     check (status in ('completed', 'failed')),
    -- Forecasts stay unpublished until the model is validated (Milestone 6)
    -- and rules are verified from primary sources (Milestone 7 gate).
    is_published     boolean not null default false,
    notes            jsonb not null default '[]'::jsonb
);

create index model_runs_season_idx on model_runs (season_id, run_at desc);

create table season_forecasts (
    model_run_id       bigint not null references model_runs (id) on delete cascade,
    team_id            integer not null references teams (id),
    current_points     smallint not null,
    played             smallint not null,
    expected_points    double precision not null,
    expected_position  double precision not null,
    position_probs     double precision[] not null,   -- index 1 = P(1st), ...
    zone_probs         jsonb not null,                -- {"champion": 0.42, "relegation": 0.01, ...}
    primary key (model_run_id, team_id)
);

create table match_forecasts (
    id             bigint generated always as identity primary key,
    model_run_id   bigint not null references model_runs (id) on delete cascade,
    fixture_id     bigint references fixtures (id),   -- NULL: fixture missing from provider list
    home_team_id   integer not null references teams (id),
    away_team_id   integer not null references teams (id),
    p_home         double precision not null check (p_home between 0 and 1),
    p_draw         double precision not null check (p_draw between 0 and 1),
    p_away         double precision not null check (p_away between 0 and 1),
    xg_home        double precision not null check (xg_home >= 0),
    xg_away        double precision not null check (xg_away >= 0),
    check (abs(p_home + p_draw + p_away - 1) < 1e-6),
    unique (model_run_id, home_team_id, away_team_id)
);

alter table model_runs        enable row level security;
alter table season_forecasts  enable row level security;
alter table match_forecasts   enable row level security;
