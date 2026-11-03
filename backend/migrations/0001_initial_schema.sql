-- ============================================================================
-- 0001 — Source-data schema (Milestone 2)
--
-- Holds provider data only. Model outputs (ratings, forecasts, backtests) get
-- their own tables in later migrations and never overwrite these.
--
-- Unqualified names on purpose: tables land in the current search_path, which
-- lets the integration tests build this schema in a throwaway namespace.
-- ============================================================================

create table competitions (
    id          smallint generated always as identity primary key,
    code        text not null unique,                 -- internal code, e.g. 'EPL'
    name        text not null,
    format      text not null check (format in ('domestic_league', 'champions_league')),
    country     text,
    created_at  timestamptz not null default now()
);

create table competition_provider_ids (
    competition_id  smallint not null references competitions (id) on delete cascade,
    provider        text not null,
    external_id     text not null,
    primary key (provider, external_id),
    unique (competition_id, provider)
);

create table seasons (
    id              integer generated always as identity primary key,
    competition_id  smallint not null references competitions (id),
    start_year      smallint not null check (start_year between 1850 and 2100),
    start_date      date,
    end_date        date,
    created_at      timestamptz not null default now(),
    unique (competition_id, start_year),
    check (end_date is null or start_date is null or end_date >= start_date)
);

create table teams (
    id          integer generated always as identity primary key,
    name        text not null check (length(trim(name)) > 0),
    short_name  text,
    tla         text,
    country     text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table team_provider_ids (
    team_id      integer not null references teams (id) on delete cascade,
    provider     text not null,
    external_id  text not null,
    primary key (provider, external_id),
    unique (team_id, provider)
);

-- Which teams take part in which season (from the provider's team list).
create table season_teams (
    season_id  integer not null references seasons (id) on delete cascade,
    team_id    integer not null references teams (id),
    primary key (season_id, team_id)
);

create table ingestion_runs (
    id                 bigint generated always as identity primary key,
    provider           text not null,
    competition_id     smallint references competitions (id),
    season_id          integer references seasons (id),
    started_at         timestamptz not null default now(),
    finished_at        timestamptz,
    status             text not null default 'running'
                       check (status in ('running', 'succeeded', 'partial', 'failed')),
    request_count      integer not null default 0,
    fixtures_inserted  integer not null default 0,
    fixtures_updated   integer not null default 0,
    issues             jsonb not null default '[]'::jsonb,   -- skipped/invalid records
    consistency        jsonb,                                -- standings cross-check result
    error              text
);

create table fixtures (
    id                    bigint generated always as identity primary key,
    season_id             integer not null references seasons (id),
    home_team_id          integer not null references teams (id),
    away_team_id          integer not null references teams (id),
    kickoff_utc           timestamptz,
    status                text not null check (status in (
                              'scheduled', 'in_progress', 'finished', 'suspended', 'postponed',
                              'cancelled', 'abandoned', 'awarded', 'unknown')),
    stage                 text not null check (stage in (
                              'regular_season', 'league_stage', 'playoffs', 'last_16',
                              'quarter_finals', 'semi_finals', 'final', 'group_stage', 'other')),
    group_name            text,
    matchday              smallint check (matchday >= 1),
    -- Goals in play incl. extra time, EXCLUDING any shootout. NULL = no score (≠ 0).
    home_score            smallint check (home_score >= 0),
    away_score            smallint check (away_score >= 0),
    duration              text not null default 'regular'
                          check (duration in ('regular', 'extra_time', 'penalty_shootout')),
    home_score_90         smallint check (home_score_90 >= 0),
    away_score_90         smallint check (away_score_90 >= 0),
    home_penalties        smallint check (home_penalties >= 0),
    away_penalties        smallint check (away_penalties >= 0),
    provider              text not null,
    provider_fixture_id   text not null,
    provider_status       text,
    first_seen_run_id     bigint references ingestion_runs (id),
    last_updated_run_id   bigint references ingestion_runs (id),
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now(),

    unique (provider, provider_fixture_id),
    check (home_team_id <> away_team_id),
    check ((home_score is null) = (away_score is null)),
    check ((home_score_90 is null) = (away_score_90 is null)),
    check ((home_penalties is null) = (away_penalties is null)),
    check (status not in ('finished', 'awarded') or home_score is not null),
    check (status not in ('scheduled', 'postponed', 'cancelled') or home_score is null),
    check (duration = 'penalty_shootout' or home_penalties is null),
    check (duration = 'regular' or home_score_90 is not null)
);

create index fixtures_season_idx   on fixtures (season_id);
create index fixtures_kickoff_idx  on fixtures (kickoff_utc);
create index fixtures_home_idx     on fixtures (home_team_id);
create index fixtures_away_idx     on fixtures (away_team_id);

-- Provider-reported tables, kept per ingestion run for auditing.
create table standings_snapshots (
    id                bigint generated always as identity primary key,
    season_id         integer not null references seasons (id),
    ingestion_run_id  bigint not null references ingestion_runs (id),
    captured_at       timestamptz not null default now()
);

create table standings_rows (
    snapshot_id    bigint not null references standings_snapshots (id) on delete cascade,
    team_id        integer not null references teams (id),
    position       smallint not null check (position >= 1),
    played         smallint not null check (played >= 0),
    won            smallint not null check (won >= 0),
    drawn          smallint not null check (drawn >= 0),
    lost           smallint not null check (lost >= 0),
    goals_for      smallint not null check (goals_for >= 0),
    goals_against  smallint not null check (goals_against >= 0),
    points         smallint not null,            -- may be negative after deductions
    primary key (snapshot_id, team_id),
    check (won + drawn + lost = played)
);

-- ----------------------------------------------------------------------------
-- Row-level security: ON for every table, with NO policies. That blocks the
-- public anon/authenticated roles that Supabase exposes over its REST API.
-- The backend connects as the table owner, which bypasses RLS.
-- ----------------------------------------------------------------------------
alter table competitions              enable row level security;
alter table competition_provider_ids  enable row level security;
alter table seasons                   enable row level security;
alter table teams                     enable row level security;
alter table team_provider_ids         enable row level security;
alter table season_teams              enable row level security;
alter table ingestion_runs            enable row level security;
alter table fixtures                  enable row level security;
alter table standings_snapshots       enable row level security;
alter table standings_rows            enable row level security;
