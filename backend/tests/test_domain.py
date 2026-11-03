"""Tests for the canonical domain contracts (app/domain/models.py)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.domain.models import (
    Competition,
    CompetitionFormat,
    DomainValidationError,
    Fixture,
    FixtureStatus,
    LeagueRules,
    ProviderRef,
    Season,
    StandingRow,
    Team,
    Tiebreaker,
    Zone,
)

KICKOFF = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)


def fixture(**overrides: object) -> Fixture:
    base: dict[str, object] = {
        "season_id": 1,
        "home_team_id": 10,
        "away_team_id": 20,
        "kickoff_utc": KICKOFF,
        "status": FixtureStatus.SCHEDULED,
    }
    base.update(overrides)
    return Fixture(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------
class TestFixture:
    def test_scheduled_fixture_without_score(self) -> None:
        f = fixture()
        assert f.is_to_be_played and not f.is_completed and not f.has_valid_score

    def test_finished_fixture_with_score(self) -> None:
        f = fixture(status=FixtureStatus.FINISHED, home_score=2, away_score=1)
        assert f.is_completed and f.has_valid_score and not f.is_to_be_played

    def test_nil_nil_is_a_real_score(self) -> None:
        f = fixture(status=FixtureStatus.FINISHED, home_score=0, away_score=0)
        assert f.has_valid_score

    def test_same_team_home_and_away_rejected(self) -> None:
        with pytest.raises(DomainValidationError, match="same team"):
            fixture(away_team_id=10)

    def test_finished_without_score_rejected(self) -> None:
        with pytest.raises(DomainValidationError, match="must have a score"):
            fixture(status=FixtureStatus.FINISHED)

    def test_awarded_without_score_rejected(self) -> None:
        with pytest.raises(DomainValidationError, match="must have a score"):
            fixture(status=FixtureStatus.AWARDED)

    @pytest.mark.parametrize(
        "status", [FixtureStatus.SCHEDULED, FixtureStatus.POSTPONED, FixtureStatus.CANCELLED]
    )
    def test_unplayed_fixture_with_score_rejected(self, status: FixtureStatus) -> None:
        with pytest.raises(DomainValidationError, match="cannot have a score"):
            fixture(status=status, home_score=1, away_score=0)

    def test_half_a_score_rejected(self) -> None:
        with pytest.raises(DomainValidationError, match="both scores or neither"):
            fixture(status=FixtureStatus.FINISHED, home_score=1)

    def test_negative_score_rejected(self) -> None:
        with pytest.raises(DomainValidationError, match="non-negative"):
            fixture(status=FixtureStatus.FINISHED, home_score=-1, away_score=0)

    def test_naive_kickoff_rejected(self) -> None:
        with pytest.raises(DomainValidationError, match="timezone-aware"):
            fixture(kickoff_utc=datetime(2026, 8, 22, 14, 0))

    def test_kickoff_normalized_to_utc(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        f = fixture(kickoff_utc=datetime(2026, 8, 22, 19, 30, tzinfo=ist))
        assert f.kickoff_utc == KICKOFF
        assert f.kickoff_utc is not None and f.kickoff_utc.utcoffset() == timedelta(0)

    def test_unknown_kickoff_allowed(self) -> None:
        assert fixture(kickoff_utc=None).kickoff_utc is None

    def test_postponed_still_to_be_played(self) -> None:
        assert fixture(status=FixtureStatus.POSTPONED).is_to_be_played

    @pytest.mark.parametrize(
        "status", [FixtureStatus.CANCELLED, FixtureStatus.UNKNOWN, FixtureStatus.IN_PROGRESS]
    )
    def test_not_simulated(self, status: FixtureStatus) -> None:
        assert not fixture(status=status).is_to_be_played

    def test_immutable(self) -> None:
        f = fixture()
        with pytest.raises(AttributeError):
            f.home_score = 3  # type: ignore[misc]

    def test_invalid_matchday_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            fixture(matchday=0)


# ---------------------------------------------------------------------------
# Other entities
# ---------------------------------------------------------------------------
class TestEntities:
    def test_competition(self) -> None:
        c = Competition(code="EPL", name="Premier League", format=CompetitionFormat.DOMESTIC_LEAGUE)
        assert c.id is None
        with pytest.raises(DomainValidationError):
            Competition(code="", name="x", format=CompetitionFormat.DOMESTIC_LEAGUE)

    def test_season_label(self) -> None:
        assert Season("EPL", 2026).label == "2026/27"
        assert Season("EPL", 1999).label == "1999/00"

    def test_season_dates_ordered(self) -> None:
        with pytest.raises(DomainValidationError):
            Season("EPL", 2026, start_date=date(2027, 5, 1), end_date=date(2026, 8, 1))

    def test_team_provider_lookup(self) -> None:
        t = Team(name="Arsenal FC", provider_refs=(ProviderRef("football_data_org", "57"),))
        assert t.external_id("football_data_org") == "57"
        assert t.external_id("api_football") is None

    def test_team_duplicate_provider_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            Team(name="X", provider_refs=(ProviderRef("p", "1"), ProviderRef("p", "2")))

    def test_provider_ref_requires_values(self) -> None:
        with pytest.raises(DomainValidationError):
            ProviderRef("", "1")

    def test_standing_row_consistency(self) -> None:
        row = StandingRow(
            1, 1, played=10, won=7, drawn=2, lost=1, goals_for=20, goals_against=8, points=23
        )
        assert row.goal_difference == 12
        with pytest.raises(DomainValidationError, match="!= played"):
            StandingRow(
                1, 1, played=10, won=7, drawn=2, lost=2, goals_for=20, goals_against=8, points=23
            )


# ---------------------------------------------------------------------------
# League rules (shape only — real values come from verified config)
# ---------------------------------------------------------------------------
def rules(**overrides: object) -> LeagueRules:
    base: dict[str, object] = {
        "competition_code": "TEST",
        "season_start_year": 2026,
        "team_count": 20,
        "points_for_win": 3,
        "points_for_draw": 1,
        "tiebreakers": (Tiebreaker.POINTS, Tiebreaker.GOAL_DIFFERENCE),
        "zones": (Zone("relegation", "Relegation", 18, 20),),
    }
    base.update(overrides)
    return LeagueRules(**base)  # type: ignore[arg-type]


class TestLeagueRules:
    def test_valid_rules(self) -> None:
        r = rules()
        zone = r.zone("relegation")
        assert zone is not None and zone.contains(18) and not zone.contains(17)
        assert not r.is_verified

    def test_verified_requires_source_and_date(self) -> None:
        assert rules(source="https://example.org/rules", verified_on=date(2026, 11, 3)).is_verified
        assert not rules(source="https://example.org/rules").is_verified

    def test_zone_beyond_table_rejected(self) -> None:
        with pytest.raises(DomainValidationError, match="only 20 teams"):
            rules(zones=(Zone("relegation", "Relegation", 18, 21),))

    def test_tiebreakers_must_start_with_points(self) -> None:
        with pytest.raises(DomainValidationError):
            rules(tiebreakers=(Tiebreaker.GOAL_DIFFERENCE,))

    def test_bad_points_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            rules(points_for_win=1, points_for_draw=1)

    def test_invalid_zone_range(self) -> None:
        with pytest.raises(DomainValidationError):
            Zone("x", "X", 5, 2)
