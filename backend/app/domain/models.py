"""
Final Whistle — Domain models.

Pure data classes representing the canonical internal entities.
These are independent of any provider or database schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CompetitionFormat(str, Enum):
    DOMESTIC_LEAGUE = "domestic_league"
    CHAMPIONS_LEAGUE = "champions_league"


class FixtureStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    SUSPENDED = "suspended"   # stopped mid-match; may resume or be replayed
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    AWARDED = "awarded"
    UNKNOWN = "unknown"


@dataclass
class Competition:
    id: Optional[int] = None
    name: str = ""
    code: str = ""
    format: CompetitionFormat = CompetitionFormat.DOMESTIC_LEAGUE
    country: str = ""
    provider: str = ""
    provider_competition_id: Optional[int] = None


@dataclass
class Season:
    id: Optional[int] = None
    competition_id: Optional[int] = None
    season_label: str = ""        # e.g. "2026"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    rules_config: dict = field(default_factory=dict)


@dataclass
class Team:
    id: Optional[int] = None
    name: str = ""
    short_name: str = ""
    country: str = ""
    logo_url: str = ""
    provider_team_ids: dict[str, int] = field(default_factory=dict)


@dataclass
class Fixture:
    id: Optional[int] = None
    season_id: Optional[int] = None
    home_team_id: Optional[int] = None
    away_team_id: Optional[int] = None
    kickoff_utc: Optional[datetime] = None
    status: FixtureStatus = FixtureStatus.SCHEDULED
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    matchday: Optional[int] = None
    provider: str = ""
    provider_fixture_id: Optional[int] = None

    @property
    def is_completed(self) -> bool:
        return self.status == FixtureStatus.FINISHED

    @property
    def has_valid_score(self) -> bool:
        return (
            self.is_completed
            and self.home_score is not None
            and self.away_score is not None
        )

