"""Tests for the baseline models: Elo, Elo outcome mapping, Poisson goal model."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from scipy.optimize import check_grad

from app.models.data import MatchRecord, played_before
from app.models.elo import EloParams, compute_elo, expected_home_score, margin_multiplier
from app.models.elo_outcome import fit_elo_outcomes, rating_diff
from app.models.poisson import (
    FitError,
    PoissonParams,
    fit_poisson,
    outcome_probabilities,
    score_matrix,
)

T0 = datetime(2023, 8, 1, tzinfo=UTC)
_ids = iter(range(1, 10**9))


def rec(day: int, home: int, away: int, hg: int | None, ag: int | None, *,
        comp: str = "EPL", season: int = 2023, neutral: bool = False) -> MatchRecord:  # fmt: skip
    return MatchRecord(next(_ids), T0 + timedelta(days=day), comp, season, home, away, hg, ag,
                       neutral)  # fmt: skip


def synthetic_league(seed: int = 1, n_teams: int = 10, rounds: int = 6) -> list[MatchRecord]:
    """Double round-robins with KNOWN strengths: team i has attack 0.08*(i-4.5)."""
    rng = np.random.default_rng(seed)
    att = {t: 0.08 * (t - 4.5) for t in range(n_teams)}
    out: list[MatchRecord] = []
    day = 0
    for _ in range(rounds):
        for h in range(n_teams):
            for a in range(n_teams):
                if h == a:
                    continue
                day += 1
                lh, la = np.exp(0.25 + 0.2 + att[h] - att[a]), np.exp(0.25 + att[a] - att[h])
                out.append(rec(day // 5, h, a, int(rng.poisson(lh)), int(rng.poisson(la))))
    return out


# ---------------------------------------------------------------------------
# Leakage guard
# ---------------------------------------------------------------------------
class TestPlayedBefore:
    def test_excludes_unplayed_and_future_and_boundary(self) -> None:
        recs = [rec(1, 1, 2, 1, 0), rec(5, 2, 1, None, None), rec(10, 1, 2, 0, 0)]
        cut = T0 + timedelta(days=10)  # match on day 10 kicks off AT the cutoff -> excluded
        assert [m.fixture_id for m in played_before(recs, cut)] == [recs[0].fixture_id]

    def test_naive_cutoff_rejected(self) -> None:
        with pytest.raises(ValueError):
            played_before([], datetime(2026, 1, 1))


# ---------------------------------------------------------------------------
# Elo
# ---------------------------------------------------------------------------
class TestElo:
    def test_expected_score(self) -> None:
        p = EloParams(home_advantage=0)
        assert expected_home_score(1500, 1500, p) == pytest.approx(0.5)
        assert expected_home_score(1600, 1500, p) == pytest.approx(1 / (1 + 10**-0.25))
        p2 = EloParams(home_advantage=100)
        assert expected_home_score(1500, 1500, p2, neutral=True) == pytest.approx(0.5)
        assert expected_home_score(1500, 1500, p2) > 0.5

    def test_margin_multiplier(self) -> None:
        assert [margin_multiplier(g) for g in (0, 1, -1, 2, 3, 5)] == [1, 1, 1, 1.5, 1.75, 2.0]

    def test_single_update_and_zero_sum(self) -> None:
        recs = [rec(0, 1, 2, 2, 0)]
        p = EloParams(k=20, home_advantage=0, use_margin=False)
        r = compute_elo(recs, T0 + timedelta(days=1), p)
        assert r.ratings[1] == pytest.approx(1510) and r.ratings[2] == pytest.approx(1490)
        assert r.pre_match[recs[0].fixture_id] == (1500, 1500)  # stored BEFORE the update

    def test_no_leakage_future_matches_change_nothing(self) -> None:
        past = synthetic_league(seed=3)
        cut = T0 + timedelta(days=200)
        future = [rec(400, 0, 9, 9, 0), rec(401, 9, 0, 0, 9)]
        a, b = compute_elo(past, cut), compute_elo(past + future, cut)
        assert a.ratings == b.ratings and a.pre_match == b.pre_match

    def test_order_of_input_does_not_matter(self) -> None:
        recs = synthetic_league(seed=4)
        cut = T0 + timedelta(days=999)
        assert compute_elo(recs, cut).ratings == compute_elo(list(reversed(recs)), cut).ratings

    def test_stronger_teams_rated_higher(self) -> None:
        r = compute_elo(synthetic_league(seed=5), T0 + timedelta(days=999))
        assert r.ratings[9] > r.ratings[5] > r.ratings[0]

    def test_season_regression(self) -> None:
        p = EloParams(k=20, home_advantage=0, use_margin=False, season_regression=0.5)
        recs = [rec(0, 1, 2, 1, 0, season=2023), rec(400, 1, 2, 0, 0, season=2024)]
        r = compute_elo(recs, T0 + timedelta(days=500), p)
        # after match 1: 1510 / 1490; new season regresses halfway: 1505 / 1495
        assert r.pre_match[recs[1].fixture_id] == pytest.approx((1505, 1495))

    def test_promoted_team_inherits_relegated_average(self) -> None:
        p = EloParams(k=20, home_advantage=0, use_margin=False, season_regression=0.0)
        recs = [
            rec(0, 1, 2, 1, 0, season=2023),  # 1 -> 1510, 2 -> 1490 ; team 2 is "relegated"
            rec(1, 1, 3, 0, 0, season=2023),  # team 3 survives
            rec(400, 4, 1, 0, 0, season=2024),  # team 4 is new in 2024 -> promoted
            rec(401, 3, 4, 0, 0, season=2024),
        ]
        r = compute_elo(recs, T0 + timedelta(days=500), p)
        assert r.pre_match[recs[2].fixture_id][0] == pytest.approx(1490)
        assert r.initialised[4].startswith("promoted:EPL:2024")
        assert r.initialised[1].startswith("base:")

    def test_ucl_newcomer_starts_at_base(self) -> None:
        recs = [rec(0, 1, 2, 1, 0, comp="UCL"), rec(1, 3, 1, 0, 0, comp="UCL")]
        r = compute_elo(recs, T0 + timedelta(days=5))
        assert r.initialised[3].startswith("base:UCL")


class TestEloOutcome:
    def test_fit_and_probabilities(self) -> None:
        recs = synthetic_league(seed=6, rounds=10)
        cut = T0 + timedelta(days=999)
        elo = compute_elo(recs, cut)
        m = fit_elo_outcomes(recs, elo, cut, skip_first=90)
        for diff in (-300, 0, 65, 300):
            ph, pd, pa = m.probabilities(diff)
            assert min(ph, pd, pa) > 0 and ph + pd + pa == pytest.approx(1)
        assert m.probabilities(300)[0] > m.probabilities(0)[0] > m.probabilities(-300)[0]
        assert rating_diff(elo, 9, 0) > rating_diff(elo, 0, 9)

    def test_rejects_ratings_from_later_cutoff(self) -> None:
        recs = synthetic_league(seed=7)
        late = compute_elo(recs, T0 + timedelta(days=999))
        with pytest.raises(ValueError, match="leakage"):
            fit_elo_outcomes(recs, late, T0 + timedelta(days=100))


# ---------------------------------------------------------------------------
# Poisson
# ---------------------------------------------------------------------------
class TestPoisson:
    def test_score_matrix_normalised(self) -> None:
        m = score_matrix(1.6, 1.1, 10)
        assert m.shape == (11, 11) and m.sum() == pytest.approx(1)
        ph, pd, pa = outcome_probabilities(m)
        assert ph + pd + pa == pytest.approx(1) and ph > pa

    def test_equal_lambdas_symmetric(self) -> None:
        ph, _, pa = outcome_probabilities(score_matrix(1.3, 1.3, 10))
        assert ph == pytest.approx(pa)

    def test_recovers_known_strength_order(self) -> None:
        m = fit_poisson(synthetic_league(seed=8, rounds=10), T0 + timedelta(days=999),
                        PoissonParams(decay_per_day=0.0, l2_penalty=0.1))  # fmt: skip
        assert m.converged
        from scipy.stats import spearmanr

        teams = list(range(10))
        assert spearmanr(teams, [m.attack[t] for t in teams]).statistic > 0.9
        assert spearmanr(teams, [m.defence[t] for t in teams]).statistic > 0.9
        assert m.home_advantage == pytest.approx(0.2, abs=0.08)

    def test_gradient_matches_numerical(self) -> None:
        # Re-derive the objective by fitting with a tiny maxiter, then compare
        # analytic vs numerical gradient at a random point.
        import app.models.poisson as pm

        recs = synthetic_league(seed=9, rounds=2)
        captured: dict[str, object] = {}
        real_minimize = pm.minimize

        def spy(fun, x0, **kw):  # type: ignore[no-untyped-def]
            captured["fun"] = fun
            return real_minimize(fun, x0, **kw)

        pm.minimize = spy  # type: ignore[assignment]
        try:
            pm.fit_poisson(recs, T0 + timedelta(days=999))
        finally:
            pm.minimize = real_minimize
        fun = captured["fun"]
        x = np.random.default_rng(0).normal(0, 0.2, 2 + 2 * 10)
        err = check_grad(lambda v: fun(v)[0], lambda v: fun(v)[1], x)  # type: ignore[operator]
        assert err < 1e-3

    def test_no_leakage_and_deterministic(self) -> None:
        past = synthetic_league(seed=10)
        cut = T0 + timedelta(days=150)
        a = fit_poisson(past, cut)
        b = fit_poisson(past + [rec(900, 0, 9, 9, 0)], cut)
        assert a.attack == b.attack and a.mu == b.mu

    def test_neutral_removes_home_advantage(self) -> None:
        m = fit_poisson(synthetic_league(seed=11), T0 + timedelta(days=999))
        lh, la = m.expected_goals(3, 4, neutral=True)
        lh2, la2 = m.expected_goals(4, 3, neutral=True)
        assert (lh, la) == pytest.approx((la2, lh2))
        assert m.expected_goals(3, 4)[0] > lh

    def test_unknown_team_is_average(self) -> None:
        m = fit_poisson(synthetic_league(seed=12), T0 + timedelta(days=999))
        assert not m.knows(12345)
        assert m.expected_goals(12345, 12346, neutral=True)[0] == pytest.approx(np.exp(m.mu))

    def test_too_little_data(self) -> None:
        with pytest.raises(FitError):
            fit_poisson([rec(0, 1, 2, 1, 0)], T0 + timedelta(days=5))
