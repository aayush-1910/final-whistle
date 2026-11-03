"""
Cross-check provider standings against a table rebuilt from match results.

A mismatch means something is wrong or unusual: a missing/duplicated match,
a mis-read score, or a real-world adjustment such as a points deduction.
Mismatches are reported, never silently "fixed".

This is a validation aid, not the simulator's table logic: it does not order
teams or apply tiebreakers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.domain.models import Fixture, Outcome, Stage, StandingRow

_FIELDS = ("played", "won", "drawn", "lost", "goals_for", "goals_against", "points")
TABLE_STAGES = frozenset({Stage.REGULAR_SEASON, Stage.LEAGUE_STAGE, Stage.GROUP_STAGE})


@dataclass
class TeamRecord:
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0


@dataclass(frozen=True)
class Discrepancy:
    team_id: int
    field: str
    provider_value: int | None
    computed_value: int | None


@dataclass
class ConsistencyReport:
    teams_checked: int = 0
    discrepancies: list[Discrepancy] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.discrepancies


def build_records(
    fixtures: Iterable[Fixture], *, points_for_win: int = 3, points_for_draw: int = 1
) -> dict[int, TeamRecord]:
    """Aggregate completed table-stage fixtures into per-team records."""
    recs: dict[int, TeamRecord] = defaultdict(TeamRecord)
    for f in fixtures:
        if f.stage not in TABLE_STAGES or not f.is_completed:
            continue
        score, outcome = f.score_90, f.outcome_90
        if score is None or outcome is None:
            continue
        for team_id, gf, ga, res in (
            (f.home_team_id, score[0], score[1], outcome),
            (
                f.away_team_id,
                score[1],
                score[0],
                {Outcome.HOME: Outcome.AWAY, Outcome.AWAY: Outcome.HOME}.get(outcome, outcome),
            ),
        ):
            r = recs[team_id]
            r.played += 1
            r.goals_for += gf
            r.goals_against += ga
            if res is Outcome.HOME:  # "HOME" here means this team won
                r.won += 1
                r.points += points_for_win
            elif res is Outcome.DRAW:
                r.drawn += 1
                r.points += points_for_draw
            else:
                r.lost += 1
    return dict(recs)


def compare_with_standings(
    fixtures: Iterable[Fixture],
    standings: Iterable[StandingRow],
    *,
    points_for_win: int = 3,
    points_for_draw: int = 1,
) -> ConsistencyReport:
    computed = build_records(
        fixtures, points_for_win=points_for_win, points_for_draw=points_for_draw
    )
    report = ConsistencyReport()
    seen: set[int] = set()
    for row in standings:
        seen.add(row.team_id)
        report.teams_checked += 1
        mine = computed.get(row.team_id, TeamRecord())
        for name in _FIELDS:
            theirs, ours = getattr(row, name), getattr(mine, name)
            if theirs != ours:
                report.discrepancies.append(Discrepancy(row.team_id, name, theirs, ours))
    for team_id in computed.keys() - seen:
        report.discrepancies.append(
            Discrepancy(team_id, "missing_from_standings", None, computed[team_id].played)
        )
    return report
