"""Tests for football-data.org normalization and the standings cross-check.

Inputs are small hand-written payloads in the documented v4 shape (verified
against real responses on 2026-11-03), not copies of provider data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.domain.models import (
    FixtureStatus,
    MatchDuration,
    Stage,
    StandingRow,
)
from app.ingestion.consistency import compare_with_standings
from app.ingestion.normalize_fdo import (
    NormalizationError,
    normalize_match,
    normalize_matches,
    normalize_season,
    normalize_standings,
    normalize_team,
)

TEAM_IDS = {"57": 1, "61": 2, "65": 3}


def match(**kw: Any) -> dict[str, Any]:
    score = kw.pop("score", {"duration": "REGULAR", "fullTime": {"home": 2, "away": 1}})
    base: dict[str, Any] = {
        "id": 1000,
        "utcDate": "2026-08-21T19:00:00Z",
        "status": "FINISHED",
        "matchday": 1,
        "stage": "REGULAR_SEASON",
        "group": None,
        "homeTeam": {"id": 57, "name": "Arsenal FC"},
        "awayTeam": {"id": 61, "name": "Chelsea FC"},
        "score": score,
    }
    base.update(kw)
    return base


class TestMatch:
    def test_regular_finished(self) -> None:
        f = normalize_match(match(), TEAM_IDS, season_id=7)
        assert (f.home_team_id, f.away_team_id, f.season_id) == (1, 2, 7)
        assert (f.home_score, f.away_score) == (2, 1)
        assert f.status is FixtureStatus.FINISHED and f.duration is MatchDuration.REGULAR
        assert f.kickoff_utc == datetime(2026, 8, 21, 19, 0, tzinfo=UTC)
        assert f.provider_ref is not None and f.provider_ref.external_id == "1000"
        assert f.provider_status == "FINISHED"

    def test_scheduled_has_no_score(self) -> None:
        raw = match(
            status="TIMED", score={"duration": "REGULAR", "fullTime": {"home": None, "away": None}}
        )
        f = normalize_match(raw, TEAM_IDS, None)
        assert f.status is FixtureStatus.SCHEDULED and f.home_score is None

    def test_penalty_shootout_strips_penalties_from_score(self) -> None:
        raw = match(
            stage="FINAL",
            score={
                "duration": "PENALTY_SHOOTOUT",
                "fullTime": {"home": 5, "away": 4},
                "regularTime": {"home": 1, "away": 1},
                "extraTime": {"home": 0, "away": 0},
                "penalties": {"home": 4, "away": 3},
            },
        )
        f = normalize_match(raw, TEAM_IDS, None)
        assert (f.home_score, f.away_score) == (1, 1)
        assert (f.home_penalties, f.away_penalties) == (4, 3)
        assert f.score_90 == (1, 1) and f.stage is Stage.FINAL
        assert f.shootout_winner_team_id == 1

    def test_extra_time(self) -> None:
        raw = match(
            score={
                "duration": "EXTRA_TIME",
                "fullTime": {"home": 3, "away": 2},
                "regularTime": {"home": 3, "away": 0},
                "extraTime": {"home": 0, "away": 2},
            }
        )
        f = normalize_match(raw, TEAM_IDS, None)
        assert (f.home_score, f.away_score) == (3, 2)
        assert f.score_90 == (3, 0)

    def test_inconsistent_full_time_rejected(self) -> None:
        raw = match(
            score={
                "duration": "EXTRA_TIME",
                "fullTime": {"home": 9, "away": 2},
                "regularTime": {"home": 1, "away": 1},
                "extraTime": {"home": 1, "away": 1},
            }
        )
        with pytest.raises(NormalizationError, match="fullTime"):
            normalize_match(raw, TEAM_IDS, None)

    def test_unmapped_team_rejected(self) -> None:
        with pytest.raises(NormalizationError, match="Unmapped"):
            normalize_match(match(awayTeam={"id": 999}), TEAM_IDS, None)

    def test_unknown_stage_maps_to_other(self) -> None:
        assert normalize_match(match(stage="NEW_THING"), TEAM_IDS, None).stage is Stage.OTHER

    def test_matchday_zero_means_none(self) -> None:
        # Real case: UCL 2024/25 final has matchday 0.
        assert normalize_match(match(stage="FINAL", matchday=0), TEAM_IDS, None).matchday is None

    def test_group_kept(self) -> None:
        f = normalize_match(match(stage="GROUP_STAGE", group="GROUP_A"), TEAM_IDS, None)
        assert f.stage is Stage.GROUP_STAGE and f.group == "GROUP_A"


class TestBatch:
    def test_bad_records_become_issues(self) -> None:
        raws = [
            match(id=1),
            match(id=2, homeTeam={"id": None}, awayTeam={"id": None}),  # KO draw pending
            match(
                id=3,
                status="FINISHED",
                score={"duration": "REGULAR", "fullTime": {"home": None, "away": None}},
            ),
            match(id=4, awayTeam={"id": 57}),  # plays itself
        ]
        r = normalize_matches(raws, TEAM_IDS, None)
        assert [f.provider_ref.external_id for f in r.fixtures if f.provider_ref] == ["1"]
        kinds = {i.provider_id: i.kind for i in r.issues}
        assert kinds == {"2": "skipped", "3": "invalid", "4": "invalid"}


class TestTeamsSeasonsStandings:
    def test_team(self) -> None:
        t = normalize_team(
            {
                "id": 57,
                "name": "Arsenal FC",
                "shortName": "Arsenal",
                "tla": "ARS",
                "area": {"name": "England"},
            }
        )
        assert (t.name, t.short_name, t.tla, t.country) == (
            "Arsenal FC",
            "Arsenal",
            "ARS",
            "England",
        )
        assert t.external_id("football_data_org") == "57"

    def test_team_requires_id(self) -> None:
        with pytest.raises(NormalizationError):
            normalize_team({"name": "X"})

    def test_season(self) -> None:
        s = normalize_season("EPL", {"startDate": "2026-08-21", "endDate": "2027-05-30"})
        assert s.start_year == 2026 and s.end_date == date(2027, 5, 30) and s.label == "2026/27"

    def test_standings_uses_total_table_only(self) -> None:
        row = {
            "position": 1,
            "team": {"id": 57},
            "playedGames": 1,
            "won": 1,
            "draw": 0,
            "lost": 0,
            "points": 3,
            "goalsFor": 2,
            "goalsAgainst": 1,
        }
        raw = {
            "standings": [
                {"type": "TOTAL", "table": [row]},
                {"type": "HOME", "table": [row]},
            ]
        }
        rows = normalize_standings(raw, TEAM_IDS)
        assert len(rows) == 1 and rows[0].team_id == 1 and rows[0].points == 3


class TestConsistency:
    def _fixtures(self) -> list[Any]:
        return normalize_matches(
            [
                match(id=1),  # Arsenal 2-1 Chelsea
                match(
                    id=2,
                    homeTeam={"id": 65},
                    awayTeam={"id": 57},
                    score={"duration": "REGULAR", "fullTime": {"home": 0, "away": 0}},
                ),
                match(
                    id=3,
                    status="SCHEDULED",
                    homeTeam={"id": 61},
                    awayTeam={"id": 65},
                    score={"duration": "REGULAR", "fullTime": {"home": None, "away": None}},
                ),
            ],
            TEAM_IDS,
            None,
        ).fixtures

    def _row(
        self, team: int, pos: int, *, p: int, w: int, d: int, lo: int, gf: int, ga: int, pts: int
    ) -> StandingRow:
        return StandingRow(team, pos, p, w, d, lo, gf, ga, pts)

    def test_matching_table(self) -> None:
        rows = [
            self._row(1, 1, p=2, w=1, d=1, lo=0, gf=2, ga=1, pts=4),
            self._row(3, 2, p=1, w=0, d=1, lo=0, gf=0, ga=0, pts=1),
            self._row(2, 3, p=1, w=0, d=0, lo=1, gf=1, ga=2, pts=0),
        ]
        report = compare_with_standings(self._fixtures(), rows)
        assert report.ok and report.teams_checked == 3

    def test_points_deduction_is_flagged(self) -> None:
        rows = [
            self._row(1, 1, p=2, w=1, d=1, lo=0, gf=2, ga=1, pts=4),
            self._row(3, 2, p=1, w=0, d=1, lo=0, gf=0, ga=0, pts=1),
            self._row(2, 3, p=1, w=0, d=0, lo=1, gf=1, ga=2, pts=-3),  # deducted
        ]
        report = compare_with_standings(self._fixtures(), rows)
        assert [
            (d.team_id, d.field, d.provider_value, d.computed_value) for d in report.discrepancies
        ] == [(2, "points", -3, 0)]
