"""Version 1 of the Final Whistle API.  Read-only (README §14)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.api import queries as q
from app.api import schemas as s
from app.api.deps import get_conn
from app.models import config

router = APIRouter(prefix="/api/v1")
Conn = Annotated[psycopg.Connection[Any], Depends(get_conn)]
Preview = Annotated[
    bool,
    Query(description="Include the latest UNPUBLISHED run (clearly flagged is_published=false)"),
]
Code = Annotated[str, Path(pattern="^[A-Z_]{2,20}$", examples=["EPL", "UCL"])]
Year = Annotated[int, Path(ge=1990, le=2100, examples=[2026])]


def _or_404[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    except q.NotFoundError as e:
        raise HTTPException(404, str(e)) from None


@router.get("/competitions", response_model=list[s.CompetitionSummary], tags=["competitions"])
def competitions(conn: Conn) -> list[s.CompetitionSummary]:
    """All competitions with current season, data freshness and latest published forecast."""
    return q.list_competitions(conn)


@router.get("/competitions/{code}/seasons/{year}/standings", response_model=s.StandingsResponse,
            tags=["competitions"])  # fmt: skip
def standings(conn: Conn, code: Code, year: Year) -> s.StandingsResponse:
    """Current table (league phase for the UCL), computed from results."""
    return _or_404(lambda: q.standings(conn, code, year))


@router.get("/competitions/{code}/seasons/{year}/forecast", response_model=s.SeasonForecastResponse,
            tags=["forecasts"])  # fmt: skip
def season_forecast(
    conn: Conn, code: Code, year: Year, preview: Preview = False
) -> s.SeasonForecastResponse:
    """Latest season forecast: position, zone (title/Europe/relegation) and, for the UCL,
    round-by-round probabilities for every club."""
    return _or_404(lambda: q.season_forecast(conn, code, year, preview=preview))


@router.get("/fixtures/upcoming", response_model=list[s.FixtureOut], tags=["fixtures"])
def upcoming(
    conn: Conn,
    preview: Preview = False,
    days: Annotated[int, Query(ge=1, le=60)] = 7,
    competition: Annotated[str | None, Query(pattern="^[A-Z_]{2,20}$")] = None,
) -> list[s.FixtureOut]:
    """Fixtures in the next ``days`` days with home/draw/away probabilities where available."""
    return q.upcoming_fixtures(conn, days=days, competition_code=competition, preview=preview)


@router.get("/fixtures/{fixture_id}", response_model=s.FixtureDetail, tags=["fixtures"])
def fixture(
    conn: Conn, fixture_id: Annotated[int, Path(ge=1)], preview: Preview = False
) -> s.FixtureDetail:
    """One fixture: result or forecast, expected goals, likely scorelines and score grid."""
    return _or_404(lambda: q.fixture_detail(conn, fixture_id, preview=preview))


@router.get("/fixtures/{fixture_id}/forecast", response_model=s.FixtureDetail, tags=["fixtures"])
def fixture_forecast(
    conn: Conn, fixture_id: Annotated[int, Path(ge=1)], preview: Preview = False
) -> s.FixtureDetail:
    """Alias of /fixtures/{id} (README §14 naming)."""
    return _or_404(lambda: q.fixture_detail(conn, fixture_id, preview=preview))


@router.get("/teams/{team_id}", response_model=s.TeamDetail, tags=["teams"])
def team(conn: Conn, team_id: Annotated[int, Path(ge=1)], preview: Preview = False) -> s.TeamDetail:
    """Team profile: seasons and positions, last five results, next five fixtures."""
    return _or_404(lambda: q.team_detail(conn, team_id, preview=preview))


@router.get(
    "/teams/{team_id}/forecast-history", response_model=s.TeamForecastHistory, tags=["teams"]
)
def team_history(
    conn: Conn,
    team_id: Annotated[int, Path(ge=1)],
    competition: Annotated[str, Query(pattern="^[A-Z_]{2,20}$")],
    season: Annotated[int, Query(ge=1990, le=2100)],
    preview: Preview = False,
) -> s.TeamForecastHistory:
    """How a team's forecast evolved run by run in one competition-season."""
    return _or_404(
        lambda: q.team_forecast_history(conn, team_id, competition, season, preview=preview)
    )


@router.get("/models/versions", response_model=list[s.ModelVersion], tags=["models"])
def versions(conn: Conn) -> list[s.ModelVersion]:
    return q.model_versions(conn, config.MODEL_VERSION)


@router.get("/models/performance", response_model=s.PerformanceResponse, tags=["models"])
def performance(conn: Conn) -> s.PerformanceResponse:
    """Latest stored backtests: match-level (H/D/A) and season-level (title/top-4/relegation)."""
    return q.performance(conn, config.MODEL_VERSION)


@router.get("/forecasts/{run_id}", response_model=s.ForecastRunResponse, tags=["forecasts"])
def forecast_run(conn: Conn, run_id: Annotated[int, Path(ge=1)]) -> s.ForecastRunResponse:
    """A specific forecast run by id (published or not; the run says which)."""
    return _or_404(lambda: q.forecast_run(conn, run_id))
