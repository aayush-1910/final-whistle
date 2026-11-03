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
    MatchDuration,
    Outcome,
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

    def test_in_progress_treated_as_unplayed(self) -> None:
        # Decision 2026-11-03: a live match is simulated from scratch; its
        # partial score is ignored and it does not count in the table yet.
        f = fixture(status=FixtureStatus.IN_PROGRESS, home_score=1, away_score=0)
        assert f.is_to_be_played and not f.is_completed

    @pytest.mark.parametrize(
        "status", [FixtureStatus.CANCELLED, FixtureStatus.UNKNOWN, FixtureStatus.SUSPENDED]
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


# ---------------------------------------------------------------------------
# Extra time and penalties
# ---------------------------------------------------------------------------
FIN = FixtureStatus.FINISHED


class TestDurations:
    def test_regular_match_derived_fields(self) -> None:
        f = fixture(status=FIN, home_score=2, away_score=2)
        assert f.score_90 == (2, 2)
        assert f.outcome_90 is Outcome.DRAW
        assert f.winner_team_id is None

    def test_shootout_match(self) -> None:
        # 2025/26 UCL final shape: 1-1 after 90, 0-0 in ET, 4-3 on penalties.
        f = fixture(
            status=FIN,
            home_score=1,
            away_score=1,
            duration=MatchDuration.PENALTY_SHOOTOUT,
            home_score_90=1,
            away_score_90=1,
            home_penalties=4,
            away_penalties=3,
        )
        assert f.outcome_90 is Outcome.DRAW
        assert f.winner_team_id is None  # match drawn...
        assert f.shootout_winner_team_id == 10  # ...shootout won by home side

    def test_second_leg_shootout_need_not_be_level(self) -> None:
        # Real case (UCL 2023/24 R16): Arsenal 1-0 Porto after a 0-1 first leg,
        # Arsenal won 4-2 on penalties.
        f = fixture(
            status=FIN,
            home_score=1,
            away_score=0,
            duration=MatchDuration.PENALTY_SHOOTOUT,
            home_score_90=1,
            away_score_90=0,
            home_penalties=4,
            away_penalties=2,
        )
        assert f.winner_team_id == 10 and f.shootout_winner_team_id == 10

    def test_extra_time_winner(self) -> None:
        f = fixture(
            status=FIN,
            home_score=1,
            away_score=2,
            duration=MatchDuration.EXTRA_TIME,
            home_score_90=1,
            away_score_90=1,
        )
        assert f.score_90 == (1, 1) and f.outcome_90 is Outcome.DRAW
        assert f.winner_team_id == 20

    def test_second_leg_extra_time_need_not_be_level_at_90(self) -> None:
        # Two-legged tie: 3-0 at 90 levels the aggregate, ET goes 0-2.
        f = fixture(
            status=FIN,
            home_score=3,
            away_score=2,
            duration=MatchDuration.EXTRA_TIME,
            home_score_90=3,
            away_score_90=0,
        )
        assert f.score_90 == (3, 0)

    def test_regular_match_cannot_have_penalties(self) -> None:
        with pytest.raises(DomainValidationError):
            fixture(status=FIN, home_score=1, away_score=1, home_penalties=4, away_penalties=3)

    def test_shootout_cannot_end_level(self) -> None:
        with pytest.raises(DomainValidationError, match="cannot end level"):
            fixture(
                status=FIN,
                home_score=1,
                away_score=1,
                duration=MatchDuration.PENALTY_SHOOTOUT,
                home_score_90=1,
                away_score_90=1,
                home_penalties=3,
                away_penalties=3,
            )

    def test_extra_time_requires_90_score(self) -> None:
        with pytest.raises(DomainValidationError, match="90-minute score"):
            fixture(status=FIN, home_score=2, away_score=1, duration=MatchDuration.EXTRA_TIME)

    def test_90_score_cannot_exceed_final(self) -> None:
        with pytest.raises(DomainValidationError, match="exceed"):
            fixture(
                status=FIN,
                home_score=1,
                away_score=1,
                duration=MatchDuration.EXTRA_TIME,
                home_score_90=2,
                away_score_90=1,
            )

    def test_extra_time_cannot_have_penalties(self) -> None:
        with pytest.raises(DomainValidationError, match="Only a penalty"):
            fixture(
                status=FIN,
                home_score=2,
                away_score=1,
                duration=MatchDuration.EXTRA_TIME,
                home_score_90=1,
                away_score_90=1,
                home_penalties=4,
                away_penalties=3,
            )

    def test_unplayed_match_has_no_outcome(self) -> None:
        f = fixture()
        assert f.score_90 is None and f.outcome_90 is None and f.winner_team_id is None
        assert f.shootout_winner_team_id is None
