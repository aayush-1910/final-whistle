"""
Smoke tests — verify the project bootstraps correctly.
"""

from app.domain.models import (
    Competition,
    CompetitionFormat,
    Fixture,
    FixtureStatus,
    Team,
)


class TestDomainModels:
    """Basic sanity checks on domain data classes."""

    def test_competition_defaults(self):
        comp = Competition(name="Premier League", code="EPL")
        assert comp.format == CompetitionFormat.DOMESTIC_LEAGUE
        assert comp.id is None

    def test_fixture_is_completed(self):
        fix = Fixture(status=FixtureStatus.FINISHED, home_score=2, away_score=1)
        assert fix.is_completed is True
        assert fix.has_valid_score is True

    def test_fixture_not_completed(self):
        fix = Fixture(status=FixtureStatus.SCHEDULED)
        assert fix.is_completed is False
        assert fix.has_valid_score is False

    def test_fixture_finished_but_no_score(self):
        fix = Fixture(status=FixtureStatus.FINISHED)
        assert fix.is_completed is True
        assert fix.has_valid_score is False

    def test_team_provider_ids(self):
        team = Team(name="Arsenal", provider_team_ids={"api_football": 42})
        assert team.provider_team_ids["api_football"] == 42

