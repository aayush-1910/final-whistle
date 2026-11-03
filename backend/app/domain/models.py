"""
Final Whistle — canonical domain contracts.

These classes are the internal language of the app.  They are independent
of any data provider and any database.  Provider adapters translate INTO
these; the database and the models read FROM these.

Every class validates itself on construction, so invalid data fails loudly
at the boundary instead of silently corrupting a forecast.  (README §6,
"Data integrity requirements".)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum


class DomainValidationError(ValueError):
    """Raised when data violates a domain invariant."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class CompetitionFormat(StrEnum):
    DOMESTIC_LEAGUE = "domestic_league"
    CHAMPIONS_LEAGUE = "champions_league"


class FixtureStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    SUSPENDED = "suspended"  # stopped mid-match; may resume or be replayed
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    AWARDED = "awarded"  # result decided off the pitch
    UNKNOWN = "unknown"  # unrecognised provider status — never simulated


class Stage(StrEnum):
    """Competition stage.  Knockout stages are needed for the UCL."""

    REGULAR_SEASON = "regular_season"
    LEAGUE_STAGE = "league_stage"
    PLAYOFFS = "playoffs"
    LAST_16 = "last_16"
    QUARTER_FINALS = "quarter_finals"
    SEMI_FINALS = "semi_finals"
    FINAL = "final"
    GROUP_STAGE = "group_stage"  # pre-2024/25 UCL format
    OTHER = "other"


class MatchDuration(StrEnum):
    """How far a completed match went."""

    REGULAR = "regular"  # decided in 90 minutes (+ stoppage time)
    EXTRA_TIME = "extra_time"
    PENALTY_SHOOTOUT = "penalty_shootout"


class Outcome(StrEnum):
    HOME = "home"
    DRAW = "draw"
    AWAY = "away"


# Statuses where a score may exist / must exist.
_MAY_HAVE_SCORE = frozenset(
    {
        FixtureStatus.IN_PROGRESS,
        FixtureStatus.FINISHED,
        FixtureStatus.SUSPENDED,
        FixtureStatus.ABANDONED,
        FixtureStatus.AWARDED,
        FixtureStatus.UNKNOWN,
    }
)
_MUST_HAVE_SCORE = frozenset({FixtureStatus.FINISHED, FixtureStatus.AWARDED})
# Fixtures still to be played (the ones a simulation samples).  A live match
# counts as unplayed: its partial score is ignored (decision 2026-11-03).
_TO_BE_PLAYED = frozenset(
    {FixtureStatus.SCHEDULED, FixtureStatus.POSTPONED, FixtureStatus.IN_PROGRESS}
)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProviderRef:
    """Where a record came from: provider name + that provider's ID.

    IDs are stored as strings because providers disagree on ID types.
    """

    provider: str
    external_id: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise DomainValidationError("ProviderRef.provider must not be empty")
        if not str(self.external_id).strip():
            raise DomainValidationError("ProviderRef.external_id must not be empty")


def _require_utc(name: str, value: datetime | None) -> datetime | None:
    """Reject naive datetimes; normalize aware ones to UTC."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} must be timezone-aware (got naive {value!r})")
    return value.astimezone(UTC)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Competition:
    code: str  # internal code, e.g. "EPL", "UCL"
    name: str
    format: CompetitionFormat
    country: str | None = None  # None for continental competitions
    id: int | None = None  # assigned by the database

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.name.strip():
            raise DomainValidationError("Competition requires a code and a name")


@dataclass(frozen=True)
class Season:
    competition_code: str
    start_year: int  # 2026 means 2026/27
    start_date: date | None = None
    end_date: date | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if not 1850 <= self.start_year <= 2100:
            raise DomainValidationError(f"Implausible season start year: {self.start_year}")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise DomainValidationError("Season end_date is before start_date")

    @property
    def label(self) -> str:
        """Human label, e.g. '2026/27'."""
        return f"{self.start_year}/{(self.start_year + 1) % 100:02d}"


@dataclass(frozen=True)
class Team:
    name: str
    short_name: str | None = None
    tla: str | None = None  # three-letter abbreviation
    country: str | None = None
    provider_refs: tuple[ProviderRef, ...] = ()
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainValidationError("Team requires a name")
        providers = [r.provider for r in self.provider_refs]
        if len(providers) != len(set(providers)):
            raise DomainValidationError(f"Team {self.name!r} has duplicate provider refs")

    def external_id(self, provider: str) -> str | None:
        return next((r.external_id for r in self.provider_refs if r.provider == provider), None)


@dataclass(frozen=True)
class Fixture:
    """One match.  Teams are referenced by canonical team ID.

    Scores: ``None`` means "no score" and is distinct from ``0``.

    ``home_score``/``away_score`` are goals scored in play, INCLUDING extra
    time but EXCLUDING any penalty shootout (a 1-1 won 4-3 on penalties is
    stored as 1-1 with penalties 4-3).  ``home_score_90``/``away_score_90``
    hold the score after regular time and are only set when the match went
    beyond 90 minutes; use :attr:`score_90` to read it for any match.
    """

    season_id: int | None
    home_team_id: int
    away_team_id: int
    kickoff_utc: datetime | None
    status: FixtureStatus
    stage: Stage = Stage.REGULAR_SEASON
    group: str | None = None
    matchday: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    duration: MatchDuration = MatchDuration.REGULAR
    home_score_90: int | None = None
    away_score_90: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None
    provider_status: str | None = None  # original provider status, kept for audit
    provider_ref: ProviderRef | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        self._validate_core()
        self._validate_duration()

    def _validate_duration(self) -> None:
        pairs = {
            "90-minute score": (self.home_score_90, self.away_score_90),
            "penalties": (self.home_penalties, self.away_penalties),
        }
        for name, (h, a) in pairs.items():
            if (h is None) != (a is None):
                raise DomainValidationError(f"Fixture must have both {name} values or neither")
            if h is not None and (h < 0 or a < 0):  # type: ignore[operator]
                raise DomainValidationError(f"{name} must be non-negative")

        has_90 = self.home_score_90 is not None
        has_pens = self.home_penalties is not None

        if self.duration is MatchDuration.REGULAR:
            if has_90 or has_pens:
                raise DomainValidationError(
                    "A match decided in regular time has no separate 90-minute score or penalties"
                )
            return

        if self.home_score is None:
            raise DomainValidationError(f"A {self.duration} match must have a score")
        if not has_90:
            raise DomainValidationError(f"A {self.duration} match needs its 90-minute score")
        if self.home_score_90 > self.home_score or self.away_score_90 > self.away_score:  # type: ignore[operator]
            raise DomainValidationError("90-minute score cannot exceed the final score")

        if self.duration is MatchDuration.PENALTY_SHOOTOUT:
            if not has_pens:
                raise DomainValidationError("A shootout match needs penalty scores")
            if self.home_penalties == self.away_penalties:
                raise DomainValidationError("A penalty shootout cannot end level")
            # NB: the match itself need not be level — in a two-legged tie the
            # shootout settles a level AGGREGATE (e.g. 2nd leg 1-0 after a 0-1
            # first leg).  Aggregate checks belong to the knockout-tie logic.
        elif has_pens:
            raise DomainValidationError("Only a penalty-shootout match can have penalty scores")

    def _validate_core(self) -> None:
        if self.home_team_id == self.away_team_id:
            raise DomainValidationError(
                f"Fixture has the same team ({self.home_team_id}) at home and away"
            )
        object.__setattr__(self, "kickoff_utc", _require_utc("kickoff_utc", self.kickoff_utc))

        if (self.home_score is None) != (self.away_score is None):
            raise DomainValidationError("Fixture must have both scores or neither")
        has_score = self.home_score is not None
        if has_score and (self.home_score < 0 or self.away_score < 0):  # type: ignore[operator]
            raise DomainValidationError("Scores must be non-negative")
        if has_score and self.status not in _MAY_HAVE_SCORE:
            raise DomainValidationError(f"A {self.status} fixture cannot have a score")
        if not has_score and self.status in _MUST_HAVE_SCORE:
            raise DomainValidationError(f"A {self.status} fixture must have a score")
        if self.matchday is not None and self.matchday < 1:
            raise DomainValidationError("matchday must be >= 1")

    @property
    def is_completed(self) -> bool:
        """Result is final and counts toward the table."""
        return self.status in _MUST_HAVE_SCORE

    @property
    def is_to_be_played(self) -> bool:
        """Should be simulated by a forecast run."""
        return self.status in _TO_BE_PLAYED

    @property
    def has_valid_score(self) -> bool:
        return self.is_completed and self.home_score is not None

    @property
    def score_90(self) -> tuple[int, int] | None:
        """Score after regular time — the input for goal models."""
        if self.home_score_90 is not None and self.away_score_90 is not None:
            return (self.home_score_90, self.away_score_90)
        if self.home_score is not None and self.away_score is not None:
            return (self.home_score, self.away_score)
        return None

    @property
    def outcome_90(self) -> Outcome | None:
        """Result after 90 minutes (what league tables and 1X2 forecasts use)."""
        s = self.score_90
        if s is None or not self.is_completed:
            return None
        return Outcome.HOME if s[0] > s[1] else Outcome.AWAY if s[1] > s[0] else Outcome.DRAW

    @property
    def winner_team_id(self) -> int | None:
        """Team that scored more goals in this match (incl. extra time); None if level.

        Penalties are NOT included: in a two-legged tie the shootout decides the
        tie, not the match.  See :attr:`shootout_winner_team_id`.
        """
        if not self.is_completed or self.home_score is None or self.away_score is None:
            return None
        if self.home_score == self.away_score:
            return None
        return self.home_team_id if self.home_score > self.away_score else self.away_team_id

    @property
    def shootout_winner_team_id(self) -> int | None:
        """Winner of the penalty shootout, if one took place."""
        if self.home_penalties is None or self.away_penalties is None:
            return None
        return self.home_team_id if self.home_penalties > self.away_penalties else self.away_team_id


@dataclass(frozen=True)
class StandingRow:
    """One row of a provider-reported table, kept to cross-check our own tables."""

    team_id: int
    position: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int

    def __post_init__(self) -> None:
        if (
            min(
                self.position,
                self.played,
                self.won,
                self.drawn,
                self.lost,
                self.goals_for,
                self.goals_against,
            )
            < 0
            or self.position < 1
        ):
            raise DomainValidationError(f"Negative/zero values in standing row: {self}")
        if self.won + self.drawn + self.lost != self.played:
            raise DomainValidationError(
                f"Standing row W+D+L ({self.won}+{self.drawn}+{self.lost}) != played "
                f"({self.played}) for team {self.team_id}"
            )

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


# ---------------------------------------------------------------------------
# Season rules — the SHAPE is defined here; actual values per season live in
# configuration and must be verified from official sources (Milestone 4/5).
# ---------------------------------------------------------------------------
class Tiebreaker(StrEnum):
    POINTS = "points"
    GOAL_DIFFERENCE = "goal_difference"
    GOALS_FOR = "goals_for"
    AWAY_GOALS_FOR = "away_goals_for"
    WINS = "wins"
    AWAY_WINS = "away_wins"
    HEAD_TO_HEAD_POINTS = "head_to_head_points"
    HEAD_TO_HEAD_GOAL_DIFFERENCE = "head_to_head_goal_difference"
    HEAD_TO_HEAD_GOALS_FOR = "head_to_head_goals_for"
    HEAD_TO_HEAD_AWAY_GOALS_FOR = "head_to_head_away_goals_for"
    OPPONENTS_POINTS = "opponents_points"  # UCL league phase
    OPPONENTS_GOAL_DIFFERENCE = "opponents_goal_difference"
    OPPONENTS_GOALS_FOR = "opponents_goals_for"
    DISCIPLINARY_POINTS = "disciplinary_points"
    UEFA_COEFFICIENT = "uefa_coefficient"
    PLAYOFF = "playoff"  # decided by a play-off match
    UNRESOLVED = "unresolved"  # data unavailable → random draw, flagged


@dataclass(frozen=True)
class Zone:
    """A named range of final positions, e.g. relegation = 18–20."""

    key: str  # e.g. "champions_league", "relegation"
    label: str
    first_position: int
    last_position: int

    def __post_init__(self) -> None:
        if not 1 <= self.first_position <= self.last_position:
            raise DomainValidationError(f"Invalid zone range for {self.key!r}")

    def contains(self, position: int) -> bool:
        return self.first_position <= position <= self.last_position


@dataclass(frozen=True)
class LeagueRules:
    competition_code: str
    season_start_year: int
    team_count: int
    points_for_win: int
    points_for_draw: int
    tiebreakers: tuple[Tiebreaker, ...]
    zones: tuple[Zone, ...] = ()
    source: str = ""  # URL/document the rules were verified against
    verified_on: date | None = None
    notes: str = ""
    points_for_loss: int = 0
    # "primary" = the official regulation itself was read; "secondary" = a
    # reputable summary that cites it (e.g. Wikipedia).  Publishing should
    # require primary (Milestone 7 gate).
    source_quality: str = "secondary"
    # Positions where a points tie is settled by a play-off match instead of
    # the tiebreakers (e.g. Serie A: 1st and 17th).
    playoff_positions: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.source_quality not in ("primary", "secondary"):
            raise DomainValidationError("source_quality must be 'primary' or 'secondary'")
        for pos in self.playoff_positions:
            if not 1 <= pos < self.team_count:
                raise DomainValidationError(f"Invalid play-off position {pos}")
        if self.team_count < 2:
            raise DomainValidationError("team_count must be >= 2")
        if not self.points_for_win > self.points_for_draw >= self.points_for_loss:
            raise DomainValidationError("Expected points: win > draw >= loss")
        if not self.tiebreakers or self.tiebreakers[0] != Tiebreaker.POINTS:
            raise DomainValidationError("Tiebreakers must start with POINTS")
        if len(set(self.tiebreakers)) != len(self.tiebreakers):
            raise DomainValidationError("Duplicate tiebreakers")
        keys = [z.key for z in self.zones]
        if len(keys) != len(set(keys)):
            raise DomainValidationError("Duplicate zone keys")
        for z in self.zones:
            if z.last_position > self.team_count:
                raise DomainValidationError(
                    f"Zone {z.key!r} ends at {z.last_position} but only {self.team_count} teams"
                )

    @property
    def is_verified(self) -> bool:
        """Rules without a source + date must not drive published forecasts."""
        return bool(self.source) and self.verified_on is not None

    def zone(self, key: str) -> Zone | None:
        return next((z for z in self.zones if z.key == key), None)


__all__ = [
    "Competition",
    "CompetitionFormat",
    "DomainValidationError",
    "Fixture",
    "FixtureStatus",
    "LeagueRules",
    "MatchDuration",
    "Outcome",
    "ProviderRef",
    "Season",
    "Stage",
    "StandingRow",
    "Team",
    "Tiebreaker",
    "Zone",
]
