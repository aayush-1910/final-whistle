"""
Normalize football-data.org v4 JSON into canonical domain objects.

Pure functions: no network, no database.  Team references are resolved
through a ``team_ids`` mapping (football-data.org team ID -> canonical ID)
supplied by the caller, so this module never invents identities.

Score semantics (verified 2026-11-03 against every non-regular finished
match in the 2023-2026 data, 0 violations):
    fullTime = regularTime + extraTime + penalties
So for a shootout match ``fullTime`` is NOT the goals scored; the shootout
is stripped out here and stored separately.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain.models import (
    DomainValidationError,
    Fixture,
    FixtureStatus,
    MatchDuration,
    ProviderRef,
    Season,
    Stage,
    StandingRow,
    Team,
)
from app.providers.football_data_org import PROVIDER_NAME, normalize_status

logger = logging.getLogger(__name__)

STAGE_MAP: dict[str, Stage] = {
    "REGULAR_SEASON": Stage.REGULAR_SEASON,
    "LEAGUE_STAGE": Stage.LEAGUE_STAGE,
    "GROUP_STAGE": Stage.GROUP_STAGE,
    "PLAYOFFS": Stage.PLAYOFFS,
    "LAST_16": Stage.LAST_16,
    "QUARTER_FINALS": Stage.QUARTER_FINALS,
    "SEMI_FINALS": Stage.SEMI_FINALS,
    "FINAL": Stage.FINAL,
}

DURATION_MAP: dict[str, MatchDuration] = {
    "REGULAR": MatchDuration.REGULAR,
    "EXTRA_TIME": MatchDuration.EXTRA_TIME,
    "PENALTY_SHOOTOUT": MatchDuration.PENALTY_SHOOTOUT,
}

# Statuses where the provider's score is meaningful enough to keep.
_SCORED = frozenset(
    {
        FixtureStatus.FINISHED,
        FixtureStatus.AWARDED,
        FixtureStatus.IN_PROGRESS,
        FixtureStatus.SUSPENDED,
        FixtureStatus.ABANDONED,
    }
)


_SCORE_KEYS = (
    "home_score",
    "away_score",
    "home_score_90",
    "away_score_90",
    "home_penalties",
    "away_penalties",
)


class NormalizationError(ValueError):
    """Raw provider data cannot be turned into a valid domain object."""


@dataclass(frozen=True)
class Issue:
    """A record that was skipped, and why.  Stored with the ingestion run."""

    kind: str  # "skipped" (expected, e.g. teams TBD) or "invalid" (bad data)
    provider_id: str
    message: str


@dataclass
class NormalizedMatches:
    fixtures: list[Fixture] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def _ref(raw_id: Any) -> ProviderRef:
    return ProviderRef(PROVIDER_NAME, str(raw_id))


def _pair(obj: Mapping[str, Any] | None) -> tuple[int, int] | None:
    """Return (home, away) if both are present, None if both absent."""
    if not obj:
        return None
    h, a = obj.get("home"), obj.get("away")
    if h is None and a is None:
        return None
    if h is None or a is None:
        raise NormalizationError(f"Half-missing score pair: {obj}")
    return int(h), int(a)


# ---------------------------------------------------------------------------
# Teams / seasons
# ---------------------------------------------------------------------------
def normalize_team(raw: Mapping[str, Any]) -> Team:
    if raw.get("id") is None or not raw.get("name"):
        raise NormalizationError(f"Team without id/name: {raw!r:.200}")
    area = raw.get("area") or {}
    return Team(
        name=raw["name"],
        short_name=raw.get("shortName") or None,
        tla=raw.get("tla") or None,
        country=area.get("name") or None,
        provider_refs=(_ref(raw["id"]),),
        crest_url=raw.get("crest") or None,
    )


def normalize_season(competition_code: str, raw_season: Mapping[str, Any]) -> Season:
    """``raw_season`` is a football-data.org season object (startDate/endDate)."""
    start = date.fromisoformat(raw_season["startDate"])
    end = date.fromisoformat(raw_season["endDate"]) if raw_season.get("endDate") else None
    return Season(competition_code, start.year, start_date=start, end_date=end)


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------
def _scores(raw: Mapping[str, Any], duration: MatchDuration) -> dict[str, int | None]:
    score = raw.get("score") or {}
    full = _pair(score.get("fullTime"))
    out: dict[str, int | None] = dict.fromkeys(_SCORE_KEYS)
    if full is None:
        return out

    if duration is MatchDuration.REGULAR:
        out["home_score"], out["away_score"] = full
        return out

    regular = _pair(score.get("regularTime"))
    extra = _pair(score.get("extraTime")) or (0, 0)
    pens = _pair(score.get("penalties")) or (0, 0)
    if regular is None:
        raise NormalizationError(f"{duration} match without regularTime score")
    expected = (regular[0] + extra[0] + pens[0], regular[1] + extra[1] + pens[1])
    if expected != full:
        raise NormalizationError(
            f"fullTime {full} != regularTime {regular} + extraTime {extra} + penalties {pens}"
        )
    out["home_score"], out["away_score"] = regular[0] + extra[0], regular[1] + extra[1]
    out["home_score_90"], out["away_score_90"] = regular
    if duration is MatchDuration.PENALTY_SHOOTOUT:
        out["home_penalties"], out["away_penalties"] = pens
    return out


def normalize_match(
    raw: Mapping[str, Any], team_ids: Mapping[str, int], season_id: int | None
) -> Fixture:
    """Convert one raw match.  Raises NormalizationError / DomainValidationError."""
    home_raw = (raw.get("homeTeam") or {}).get("id")
    away_raw = (raw.get("awayTeam") or {}).get("id")
    if home_raw is None or away_raw is None:
        raise NormalizationError("Teams not yet known (e.g. knockout draw pending)")
    try:
        home_id, away_id = team_ids[str(home_raw)], team_ids[str(away_raw)]
    except KeyError as e:
        raise NormalizationError(f"Unmapped provider team id {e.args[0]}") from None

    provider_status = raw.get("status")
    status = normalize_status(provider_status)

    stage_raw = raw.get("stage")
    stage = STAGE_MAP.get(stage_raw or "", Stage.OTHER)
    if stage is Stage.OTHER:
        logger.warning("Unrecognised stage %r on match %s", stage_raw, raw.get("id"))

    duration_raw = (raw.get("score") or {}).get("duration") or "REGULAR"
    if duration_raw not in DURATION_MAP:
        raise NormalizationError(f"Unrecognised duration {duration_raw!r}")
    duration = DURATION_MAP[duration_raw]

    if status in _SCORED:
        scores = _scores(raw, duration)
    else:  # no result yet → ignore any score/duration the provider sends
        scores = dict.fromkeys(_SCORE_KEYS)
        duration = MatchDuration.REGULAR

    kickoff = datetime.fromisoformat(raw["utcDate"]) if raw.get("utcDate") else None

    return Fixture(
        season_id=season_id,
        home_team_id=home_id,
        away_team_id=away_id,
        kickoff_utc=kickoff,
        status=status,
        stage=stage,
        group=raw.get("group") or None,
        # Single-match finals arrive as matchday 0 (seen: UCL 2024/25 final) -> no matchday.
        matchday=raw.get("matchday") or None,
        duration=duration,
        provider_status=provider_status,
        provider_ref=_ref(raw["id"]),
        **scores,
    )


def normalize_matches(
    raws: Iterable[Mapping[str, Any]], team_ids: Mapping[str, int], season_id: int | None
) -> NormalizedMatches:
    """Normalize many matches; bad ones become Issues instead of aborting the batch."""
    result = NormalizedMatches()
    for raw in raws:
        pid = str(raw.get("id"))
        try:
            result.fixtures.append(normalize_match(raw, team_ids, season_id))
        except NormalizationError as e:
            kind = "skipped" if "not yet known" in str(e) else "invalid"
            result.issues.append(Issue(kind, pid, str(e)))
        except (DomainValidationError, KeyError, TypeError, ValueError) as e:
            result.issues.append(Issue("invalid", pid, f"{type(e).__name__}: {e}"))
    return result


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------
def normalize_standings(raw: Mapping[str, Any], team_ids: Mapping[str, int]) -> list[StandingRow]:
    """Return rows of the TOTAL table(s).  HOME/AWAY splits are ignored."""
    rows: list[StandingRow] = []
    for table in raw.get("standings", []):
        if table.get("type") != "TOTAL":
            continue
        for r in table.get("table", []):
            tid = str(r["team"]["id"])
            if tid not in team_ids:
                raise NormalizationError(f"Standings reference unmapped team {tid}")
            rows.append(
                StandingRow(
                    team_id=team_ids[tid],
                    position=r["position"],
                    played=r["playedGames"],
                    won=r["won"],
                    drawn=r["draw"],
                    lost=r["lost"],
                    goals_for=r["goalsFor"],
                    goals_against=r["goalsAgainst"],
                    points=r["points"],
                )
            )
    return rows
