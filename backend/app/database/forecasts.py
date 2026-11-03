"""Persist model runs and season/match forecasts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import psycopg

from app.simulations.domestic import SeasonForecast
from app.simulations.ucl import UCLForecast

Conn = psycopg.Connection[Any]


def git_commit() -> str | None:
    """Current git commit of the code (None if unavailable).  Appends '-dirty'
    when there are uncommitted changes, so a run is never silently attributed
    to code that differs from the commit."""
    root = Path(__file__).resolve().parents[3]
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True,
            check=True, timeout=10,
        ).stdout.strip()  # fmt: skip
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{sha}-dirty" if dirty else sha


def save_season_forecast(
    conn: Conn,
    forecast: SeasonForecast,
    *,
    model_name: str,
    model_version: str,
    params: dict[str, Any],
    code_version: str | None,
) -> int:
    """Store one run atomically; returns the model_run id."""
    with conn.transaction():
        row = conn.execute(
            """select c.id, s.id from competitions c
                 join seasons s on s.competition_id = c.id and s.start_year = %s
                where c.code = %s""",
            (forecast.season_year, forecast.competition),
        ).fetchone()
        if row is None:
            raise LookupError(f"No season {forecast.competition} {forecast.season_year}")
        competition_id, season_id = row

        run = conn.execute(
            """insert into model_runs (model_name, model_version, params, competition_id,
                   season_id, data_cutoff, seed, simulation_count, code_version, notes)
               values (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::jsonb) returning id""",
            (
                model_name, model_version, json.dumps(params, default=str), competition_id,
                season_id, forecast.as_of, forecast.seed, forecast.n_sims, code_version,
                json.dumps(forecast.notes),
            ),
        ).fetchone()  # fmt: skip
        assert run is not None
        run_id = int(run[0])

        exp_pos = forecast.expected_position
        with conn.cursor() as cur:
            cur.executemany(
                """insert into season_forecasts (model_run_id, team_id, current_points, played,
                       expected_points, expected_position, position_probs, zone_probs,
                       round_probs)
                   values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)""",
                [
                    (
                        run_id, t, forecast.current_points[t], forecast.played[t],
                        forecast.expected_points[t], exp_pos[t],
                        [float(p) for p in forecast.position_probs[i]],
                        json.dumps({k: v[t] for k, v in forecast.zone_probs.items()}),
                        json.dumps({k: v[t] for k, v in forecast.round_probs.items()})
                        if isinstance(forecast, UCLForecast)
                        else None,
                    )
                    for i, t in enumerate(forecast.team_ids)
                ],
            )  # fmt: skip
            cur.executemany(
                """insert into match_forecasts (model_run_id, fixture_id, home_team_id,
                       away_team_id, p_home, p_draw, p_away, xg_home, xg_away)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (run_id, m.fixture_id, m.home_team_id, m.away_team_id, m.p_home, m.p_draw,
                     m.p_away, m.xg_home, m.xg_away)
                    for m in forecast.matches
                ],
            )  # fmt: skip
    return run_id
