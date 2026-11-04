"""
One forecast run for one competition-season: simulate and (optionally) store.

Shared by scripts/run_forecast.py, scripts/backfill_forecasts.py and the
scheduled refresh (app/services/refresh.py), so every path uses the same model
configuration, the same UCL handling and the same stored parameters.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import psycopg

from app.database import repository as repo
from app.database.forecasts import save_season_forecast
from app.domain.models import LeagueRules
from app.models import config
from app.models.data import MatchRecord
from app.models.poisson import PoissonModel
from app.simulations.domestic import SeasonForecast, simulate_league
from app.simulations.rules import load_rules
from app.simulations.ucl import KNOCKOUT_STAGES, load_draw, simulate_ucl


def simulate_competition(
    conn: psycopg.Connection[Any],
    records: Sequence[MatchRecord],
    model: PoissonModel,
    competition: str,
    season: int,
    as_of: datetime,
    *,
    n_sims: int,
    seed: int,
    knockout: bool = True,
) -> tuple[SeasonForecast, LeagueRules]:
    """``knockout=False`` simulates the UCL league phase onwards without real knockout
    fixtures or the draw file (used for historical backfills)."""
    rules = load_rules(competition, season)
    if competition == "UCL":
        fixtures = []
        draw = None
        if knockout:
            fixtures = [f for f in repo.load_fixtures(conn, repo.season_id(conn, "UCL", season))
                        if f.stage in KNOCKOUT_STAGES]  # fmt: skip
            draw = load_draw(season)
        forecast: SeasonForecast = simulate_ucl(
            list(records), season, model, rules, as_of, n_sims=n_sims, seed=seed,
            knockout=fixtures, draw=draw, strength_sd=config.STRENGTH_SD,
        )  # fmt: skip
    else:
        forecast = simulate_league(
            list(records), competition, season, model, rules, as_of, n_sims=n_sims, seed=seed,
            strength_sd=config.STRENGTH_SD,
        )  # fmt: skip
    return forecast, rules


def run_params(model: PoissonModel, rules: LeagueRules, **extra: Any) -> dict[str, Any]:
    """Everything needed to reproduce a run, stored with it."""
    return {
        "poisson": model.params.to_dict(),
        "poisson_fit": {"mu": model.mu, "home_advantage": model.home_advantage,
                        "matches_used": model.matches_used, "group_priors": model.priors},
        "strength_sd": config.STRENGTH_SD,
        "rules": {"tiebreakers": [t.value for t in rules.tiebreakers],
                  "playoff_positions": list(rules.playoff_positions),
                  "source": rules.source, "source_quality": rules.source_quality},
        **extra,
    }  # fmt: skip


def save_run(
    conn: psycopg.Connection[Any],
    forecast: SeasonForecast,
    model: PoissonModel,
    rules: LeagueRules,
    *,
    code_version: str | None,
    is_backfill: bool = False,
    **extra_params: Any,
) -> int:
    return save_season_forecast(
        conn, forecast, model_name=config.MODEL_NAME, model_version=config.MODEL_VERSION,
        params=run_params(model, rules, **extra_params), code_version=code_version,
        is_backfill=is_backfill,
    )  # fmt: skip
