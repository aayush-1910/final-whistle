"""
API response schemas: the contract the dashboard is built against.

Every forecast-bearing response carries a ``run`` block (model version, data
cutoff, simulation count, publication state) and every data-bearing response
carries ``freshness``, so nothing reaches a screen without saying where it came
from and how current it is (README §1 principles 1-3, §9).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

DISCLAIMER = (
    "Probabilities from a statistical model, not certainties. "
    "Final Whistle is an independent project and not a betting product."
)


class TeamRef(BaseModel):
    id: int
    name: str
    short_name: str | None = None
    tla: str | None = None
    crest_url: str | None = Field(default=None, description="Club crest image (provider URL)")


class Freshness(BaseModel):
    last_ingested_at: datetime | None = Field(
        description="When fixtures/results were last imported for this competition"
    )
    last_ingestion_status: str | None = Field(description="succeeded / partial / failed")
    is_stale: bool = Field(description="True if the last import is older than stale_after_hours")
    stale_after_hours: int


class RunInfo(BaseModel):
    run_id: int
    model_name: str
    model_version: str
    data_cutoff: datetime = Field(description="Only matches before this time were used")
    run_at: datetime
    simulation_count: int
    seed: int
    code_version: str | None
    is_published: bool = Field(description="False = preview of an unpublished run")
    is_backfill: bool = Field(
        default=False,
        description="Historical run: computed later, using only data before data_cutoff",
    )
    rules_source_quality: str | None = Field(description="primary / secondary")
    notes: list[str]


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str


class CompetitionSummary(BaseModel):
    code: str
    name: str
    format: str
    country: str | None
    emblem_url: str | None = None
    current_season: int | None
    season_label: str | None
    freshness: Freshness
    latest_published_run: RunInfo | None
    preview_run_available: bool


class StandingRow(BaseModel):
    position: int
    team: TeamRef
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: list[str] = Field(description="Last five results, oldest first: W / D / L")


class StandingsResponse(BaseModel):
    competition: str
    season: int
    season_label: str
    ordering_note: str
    freshness: Freshness
    rows: list[StandingRow]


class Zone(BaseModel):
    key: str
    label: str
    first_position: int
    last_position: int


class TeamForecast(BaseModel):
    team: TeamRef
    current_points: int
    played: int
    expected_points: float
    expected_position: float
    position_probs: list[float] = Field(description="Index 0 = P(1st), index 1 = P(2nd), ...")
    zone_probs: dict[str, float]
    round_probs: dict[str, float] | None = Field(
        default=None, description="UCL only: P(reach round), 'winner' = P(win the final)"
    )


class SeasonForecastResponse(BaseModel):
    competition: str
    season: int
    season_label: str
    run: RunInfo
    freshness: Freshness
    zones: list[Zone]
    rounds: list[str] | None
    teams: list[TeamForecast]
    disclaimer: str = DISCLAIMER


class MatchForecastOut(BaseModel):
    p_home: float
    p_draw: float
    p_away: float
    xg_home: float
    xg_away: float
    run_id: int
    model_version: str
    data_cutoff: datetime
    is_published: bool


class FixtureOut(BaseModel):
    id: int
    competition: str
    season: int
    stage: str
    matchday: int | None
    kickoff_utc: datetime | None
    status: str
    home: TeamRef
    away: TeamRef
    home_score: int | None = Field(description="Goals incl. extra time, excl. shoot-out")
    away_score: int | None
    duration: str
    home_penalties: int | None
    away_penalties: int | None
    forecast: MatchForecastOut | None


class Scoreline(BaseModel):
    home: int
    away: int
    probability: float


class FixtureDetail(FixtureOut):
    likely_scorelines: list[Scoreline] = Field(description="Most likely exact scores (top 10)")
    score_matrix: list[list[float]] | None = Field(
        description="P(home=i, away=j) for i, j in 0..5 (from the model's expected goals)"
    )
    disclaimer: str = DISCLAIMER


class TeamSeason(BaseModel):
    competition: str
    season: int
    position: int | None
    played: int
    points: int


class TeamDetail(BaseModel):
    team: TeamRef
    country: str | None
    seasons: list[TeamSeason]
    recent_results: list[FixtureOut]
    upcoming_fixtures: list[FixtureOut]


class ForecastHistoryPoint(BaseModel):
    run_id: int
    run_at: datetime
    data_cutoff: datetime
    model_version: str
    is_published: bool
    expected_position: float
    expected_points: float
    zone_probs: dict[str, float]
    round_probs: dict[str, float] | None


class TeamForecastHistory(BaseModel):
    team: TeamRef
    competition: str
    season: int
    points: list[ForecastHistoryPoint]


class ModelVersion(BaseModel):
    model_name: str
    model_version: str
    runs: int
    published_runs: int
    first_run_at: datetime
    last_run_at: datetime
    is_current: bool


class BacktestOut(BaseModel):
    backtest_id: int
    kind: str = Field(description="match (H/D/A per match) or season (title/top-4/relegation)")
    model_version: str
    run_at: datetime
    tuning_window: dict[str, object]
    test_window: dict[str, object]
    params: dict[str, object]
    metrics: dict[str, object]


class PerformanceResponse(BaseModel):
    current_model_version: str
    match_level: BacktestOut | None
    season_level: BacktestOut | None
    report: str = "docs/backtest-report.md"


class TimelinePoint(BaseModel):
    run_id: int
    data_cutoff: datetime
    matchday: int = Field(description="Matchdays completed at the data cutoff (0 = pre-season)")
    is_published: bool
    is_backfill: bool
    probs: dict[int, float] = Field(description="team id -> probability of the metric")
    expected_points: dict[int, float]


class TimelineResponse(BaseModel):
    competition: str
    season: int
    metric: str = Field(description="champion (leagues) or winner (UCL: lifts the trophy)")
    teams: list[TeamRef]
    points: list[TimelinePoint] = Field(description="One per matchday, oldest first")


class CompetitionDataStatus(BaseModel):
    code: str
    name: str
    season: int | None
    fixtures_total: int
    fixtures_played: int
    fixtures_remaining: int
    freshness: Freshness
    latest_run_id: int | None
    latest_run_cutoff: datetime | None
    latest_run_published: bool | None
    runs_total: int
    runs_published: int


class IngestionRunOut(BaseModel):
    id: int
    competition: str | None
    season: int | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    request_count: int
    fixtures_inserted: int
    fixtures_updated: int
    issues: int
    consistency_ok: bool | None
    error: str | None


class DataStatusResponse(BaseModel):
    competitions: list[CompetitionDataStatus]
    recent_ingestions: list[IngestionRunOut]


class ForecastRunResponse(BaseModel):
    competition: str
    season: int
    run: RunInfo
    teams: list[TeamForecast]
