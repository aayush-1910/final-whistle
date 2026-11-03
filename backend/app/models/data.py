"""
Model input: a flat, provider-free view of matches.

Models never see the database or the provider.  They receive MatchRecords
and an explicit ``as_of`` time, and must only learn from records whose
kickoff is strictly before ``as_of`` (see ``played_before``).  That single
rule is how the backtests avoid data leakage.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.models import FixtureStatus, Stage


@dataclass(frozen=True, slots=True)
class MatchRecord:
    fixture_id: int
    kickoff_utc: datetime
    competition: str  # internal code, e.g. "EPL"
    season_year: int  # 2026 = 2026/27
    home_team_id: int
    away_team_id: int
    home_goals: int | None  # goals after 90 minutes; None if not played
    away_goals: int | None
    neutral: bool = False  # e.g. UCL final: no home advantage

    @property
    def is_played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


def sort_key(m: MatchRecord) -> tuple[datetime, int]:
    return (m.kickoff_utc, m.fixture_id)


def played_before(records: Iterable[MatchRecord], as_of: datetime) -> list[MatchRecord]:
    """Played matches that kicked off strictly before ``as_of``, in time order.

    Every model fit goes through this function: it is the leakage guard.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return sorted((m for m in records if m.is_played and m.kickoff_utc < as_of), key=sort_key)


_COMPLETED = (FixtureStatus.FINISHED.value, FixtureStatus.AWARDED.value)


def load_match_records(conn: Any) -> list[MatchRecord]:
    """All completed matches plus all still-to-be-played matches, from the database.

    Uses the 90-minute score.  Awarded matches are included with their awarded
    score (it is the official result, though not a played football outcome).
    """
    rows: Sequence[Any] = conn.execute(
        """select f.id, f.kickoff_utc, c.code, s.start_year, f.home_team_id, f.away_team_id,
                  case when f.status in (%s, %s) then coalesce(f.home_score_90, f.home_score) end,
                  case when f.status in (%s, %s) then coalesce(f.away_score_90, f.away_score) end,
                  f.stage
             from fixtures f
             join seasons s on s.id = f.season_id
             join competitions c on c.id = s.competition_id
            where f.kickoff_utc is not null
              and f.status in ('finished', 'awarded', 'scheduled', 'postponed', 'in_progress')
            order by f.kickoff_utc, f.id""",
        (*_COMPLETED, *_COMPLETED),
    ).fetchall()
    return [
        MatchRecord(
            fixture_id=r[0],
            kickoff_utc=r[1],
            competition=r[2],
            season_year=r[3],
            home_team_id=r[4],
            away_team_id=r[5],
            home_goals=r[6],
            away_goals=r[7],
            neutral=r[8] == Stage.FINAL.value and r[2] == "UCL",
        )
        for r in rows
    ]
