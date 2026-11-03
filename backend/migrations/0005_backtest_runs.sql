-- ============================================================================
-- 0005 — Backtest results (Milestone 6)
-- One row per backtest execution, so model-performance claims always point to
-- stored evidence (README: "no performance claims without test results").
-- ============================================================================

create table backtest_runs (
    id             bigint generated always as identity primary key,
    kind           text not null check (kind in ('match', 'season')),
    model_name     text not null,
    model_version  text not null,
    params         jsonb not null,          -- settings evaluated / chosen
    tuning_window  jsonb not null,          -- {"start": ..., "end": ...}
    test_window    jsonb not null,
    metrics        jsonb not null,          -- full results incl. baselines and calibration
    run_at         timestamptz not null default now(),
    code_version   text
);

alter table backtest_runs enable row level security;
