"""
Elo team-strength ratings, computed strictly in chronological order.

One shared rating pool across all competitions: UCL matches are the only
link between the domestic leagues, so they are what makes a La Liga rating
comparable with a Bundesliga rating (decision OD-004).

Policies (decision OD-002), all parameters stored in ``EloParams``:
- First appearance in a domestic league whose previous season is in the data
  (i.e. a promoted club): start at the mean rating of the clubs that left
  that league after the previous season (the relegated clubs).
- Any other first appearance (first season of data, UCL-only clubs):
  start at ``base_rating``.
- Start of each new season: regress ``season_regression`` of the way back to
  ``base_rating`` (squads change in the summer).
- Margin of victory scales K (World Football Elo convention).

Every parameter default here is PROVISIONAL until tuned by time-ordered
backtesting in Milestone 6.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from statistics import fmean
from typing import Any

from app.models.data import MatchRecord, played_before

DOMESTIC = frozenset({"EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A"})


@dataclass(frozen=True)
class EloParams:
    base_rating: float = 1500.0
    k: float = 20.0
    home_advantage: float = 65.0  # rating points added to the home side
    use_margin: bool = True
    season_regression: float = 0.20  # fraction pulled back toward base each new season

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expected_home_score(
    home_rating: float, away_rating: float, params: EloParams, *, neutral: bool = False
) -> float:
    """Elo expected score for the home side (win=1, draw=0.5, loss=0)."""
    diff = home_rating - away_rating + (0.0 if neutral else params.home_advantage)
    return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))


def margin_multiplier(goal_diff: int) -> float:
    """World Football Elo: 1 for 0-1 goals, 1.5 for 2, (11 + n) / 8 for n >= 3."""
    n = abs(goal_diff)
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    return (11.0 + n) / 8.0


@dataclass
class EloResult:
    params: EloParams
    as_of: datetime
    ratings: dict[int, float]  # rating of every team at as_of
    pre_match: dict[int, tuple[float, float]]  # fixture_id -> (home, away) before kickoff
    matches_used: int
    initialised: dict[int, str] = field(default_factory=dict)  # team -> how it was seeded

    def rating(self, team_id: int) -> float:
        """Rating at as_of; unseen teams get the base rating."""
        return self.ratings.get(team_id, self.params.base_rating)


def compute_elo(
    records: Sequence[MatchRecord], as_of: datetime, params: EloParams | None = None
) -> EloResult:
    """Ratings using ONLY matches that kicked off before ``as_of``."""
    p = params or EloParams()
    matches = played_before(records, as_of)

    participants: dict[tuple[str, int], set[int]] = defaultdict(set)
    for m in matches:
        participants[(m.competition, m.season_year)].update((m.home_team_id, m.away_team_id))

    ratings: dict[int, float] = {}
    last_season: dict[int, int] = {}
    initialised: dict[int, str] = {}
    pre_match: dict[int, tuple[float, float]] = {}

    def seed(team: int, m: MatchRecord) -> float:
        prev = participants.get((m.competition, m.season_year - 1))
        if m.competition in DOMESTIC and prev:
            current = participants[(m.competition, m.season_year)]
            departed = [ratings[t] for t in prev - current if t in ratings]
            if departed:
                initialised[team] = f"promoted:{m.competition}:{m.season_year}"
                return fmean(departed)
        initialised[team] = f"base:{m.competition}:{m.season_year}"
        return p.base_rating

    def current(team: int, m: MatchRecord) -> float:
        if team not in ratings:
            ratings[team] = seed(team, m)
        elif last_season[team] < m.season_year:
            ratings[team] = p.base_rating + (1 - p.season_regression) * (
                ratings[team] - p.base_rating
            )
        last_season[team] = max(last_season.get(team, m.season_year), m.season_year)
        return ratings[team]

    for m in matches:
        rh, ra = current(m.home_team_id, m), current(m.away_team_id, m)
        pre_match[m.fixture_id] = (rh, ra)
        assert m.home_goals is not None and m.away_goals is not None
        actual = (
            1.0 if m.home_goals > m.away_goals else 0.5 if m.home_goals == m.away_goals else 0.0
        )
        k = p.k * (margin_multiplier(m.home_goals - m.away_goals) if p.use_margin else 1.0)
        delta = k * (actual - expected_home_score(rh, ra, p, neutral=m.neutral))
        ratings[m.home_team_id] = rh + delta
        ratings[m.away_team_id] = ra - delta

    return EloResult(p, as_of, ratings, pre_match, len(matches), initialised)
