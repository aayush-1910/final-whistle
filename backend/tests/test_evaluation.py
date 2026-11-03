"""Tests for scoring rules, the walk-forward harness, group priors, and strength uncertainty."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from itertools import permutations

import numpy as np
import pytest
from scipy.optimize import check_grad

from app.evaluation.backtest import base_rates, poisson_model, walk_forward
from app.evaluation.metrics import (
    accuracy,
    brier,
    calibration,
    expected_calibration_error,
    log_loss,
    rps,
)
from app.models.data import MatchRecord, played_before
from app.models.poisson import PoissonModel, PoissonParams, classify_teams, fit_poisson

T0 = datetime(2023, 8, 1, tzinfo=UTC)
_ids = iter(range(1, 10**9))


def rec(
    day: float,
    h: int,
    a: int,
    hg: int | None,
    ag: int | None,
    comp: str = "EPL",
    season: int = 2023,
) -> MatchRecord:
    return MatchRecord(next(_ids), T0 + timedelta(days=day), comp, season, h, a, hg, ag)


# ---------------------------------------------------------------------------
# Scoring rules
# ---------------------------------------------------------------------------
Y = np.array([0, 1, 2, 0])


def test_perfect_and_uniform_scores() -> None:
    perfect = np.eye(3)[Y]
    assert log_loss(perfect, Y) == pytest.approx(0, abs=1e-12)
    assert brier(perfect, Y) == 0 and rps(perfect, Y) == 0 and accuracy(perfect, Y) == 1
    uniform = np.full((4, 3), 1 / 3)
    assert log_loss(uniform, Y) == pytest.approx(math.log(3))
    assert brier(uniform, Y) == pytest.approx(2 / 3)


def test_rps_rewards_nearer_misses() -> None:
    y = np.array([0])  # home win happened
    near = np.array([[0.0, 1.0, 0.0]])  # predicted a draw
    far = np.array([[0.0, 0.0, 1.0]])  # predicted an away win
    assert rps(near, y) < rps(far, y)
    assert brier(near, y) == brier(far, y)  # Brier cannot tell them apart


def test_calibration_bins_and_ece() -> None:
    rng = np.random.default_rng(0)
    p = rng.dirichlet([2, 1, 1.5], size=20000)
    y = np.array([rng.choice(3, p=row) for row in p])  # outcomes drawn from the forecasts
    bins = calibration(p, y)
    assert sum(b.count for b in bins) == 3 * len(y)
    assert expected_calibration_error(p, y) < 0.015  # calibrated by construction
    overconfident = np.clip(p * 1.6 - 0.2, 0.001, None)
    overconfident /= overconfident.sum(axis=1, keepdims=True)
    assert expected_calibration_error(overconfident, y) > 0.03


def test_invalid_inputs_rejected() -> None:
    with pytest.raises(ValueError):
        log_loss(np.array([[0.5, 0.5, 0.5]]), np.array([0]))
    with pytest.raises(ValueError):
        brier(np.zeros((0, 3)), np.zeros(0, dtype=np.int64))


# ---------------------------------------------------------------------------
# Walk-forward harness: no leakage
# ---------------------------------------------------------------------------
def league(days: int = 300) -> list[MatchRecord]:
    rng = np.random.default_rng(1)
    teams = range(8)
    out = []
    for d in range(days):
        h, a = rng.choice(teams, 2, replace=False)
        out.append(rec(d, int(h), int(a), int(rng.poisson(1.5)), int(rng.poisson(1.1))))
    return out


def test_walk_forward_never_trains_on_the_future() -> None:
    recs = league()
    seen: list[tuple[datetime, datetime | None]] = []

    def spy_factory(records: Sequence[MatchRecord], as_of: datetime):  # type: ignore[no-untyped-def]
        train = played_before(records, as_of)
        seen.append((as_of, max(m.kickoff_utc for m in train) if train else None))

        def predict(ms: Sequence[MatchRecord]) -> np.ndarray:
            assert all(m.kickoff_utc >= as_of for m in ms)  # predicting only the future
            return np.full((len(ms), 3), 1 / 3)

        return predict

    start, end = T0 + timedelta(days=100), T0 + timedelta(days=200)
    res = walk_forward(recs, {"spy": spy_factory}, start, end)
    assert res.cutoffs == len(seen) > 10
    assert all(last is None or last < cut for cut, last in seen)
    assert all(start <= m.kickoff_utc < end for m in res.matches)
    assert len(res.outcomes) == len(res.matches) == res.p("spy").shape[0]


def test_walk_forward_real_models_run() -> None:
    recs = league(400)
    res = walk_forward(recs, {"base": base_rates(), "poisson": poisson_model(PoissonParams())},
                       T0 + timedelta(days=200), T0 + timedelta(days=260))  # fmt: skip
    for name in ("base", "poisson"):
        assert np.allclose(res.p(name).sum(axis=1), 1)


# ---------------------------------------------------------------------------
# Group priors
# ---------------------------------------------------------------------------
def test_classify_teams() -> None:
    ms = [
        rec(0, 1, 2, 1, 0, season=2023),  # 1, 2 established
        rec(400, 1, 3, 1, 0, season=2024),  # 3 first appears in 2024 -> promoted
        rec(401, 1, 9, 1, 0, comp="UCL", season=2024),  # 9 only in UCL
    ]
    assert classify_teams(ms) == {1: "established", 2: "established", 3: "promoted", 9: "ucl_only"}


def promoted_league() -> list[MatchRecord]:
    """Teams 0-7 established in 2023; 8-9 arrive in 2024 and are much weaker."""
    rng = np.random.default_rng(5)
    strength = {t: 0.0 for t in range(10)} | {8: -0.6, 9: -0.6}
    out = []
    for season, teams, offset in ((2023, range(8), 0), (2024, range(10), 365)):
        for i, (h, a) in enumerate(permutations(teams, 2)):
            lh = np.exp(0.3 + 0.2 + strength[h] - strength[a])
            la = np.exp(0.3 + strength[a] - strength[h])
            out.append(
                rec(
                    offset + i * 0.5,
                    h,
                    a,
                    int(rng.poisson(lh)),
                    int(rng.poisson(la)),
                    season=season,
                )
            )
    return out


def test_group_priors_learn_that_promoted_clubs_are_weaker() -> None:
    m = fit_poisson(
        promoted_league(),
        T0 + timedelta(days=800),
        PoissonParams(group_priors=True, decay_per_day=0),
    )
    assert m.converged and m.groups[8] == "promoted"
    att, dfn = m.priors["promoted"]
    assert att < -0.1 and dfn < -0.1
    # An unseen club in a domestic league starts from the promoted mean, not from average.
    assert m.effects(12345, "EPL") == m.priors["promoted"]
    assert m.effects(12345, "UCL") == m.priors["ucl_only"]
    assert m.effects(12345) == (0.0, 0.0)


def test_group_prior_gradient_matches_numerical() -> None:
    import app.models.poisson as pm

    captured: dict[str, object] = {}
    real = pm.minimize

    def spy(fun, x0, **kw):  # type: ignore[no-untyped-def]
        captured["fun"], captured["n"] = fun, len(x0)
        return real(fun, x0, **kw)

    pm.minimize = spy  # type: ignore[assignment]
    try:
        pm.fit_poisson(
            promoted_league(), T0 + timedelta(days=800), PoissonParams(group_priors=True)
        )
    finally:
        pm.minimize = real
    fun = captured["fun"]
    x = np.random.default_rng(0).normal(0, 0.2, int(captured["n"]))  # type: ignore[call-overload]
    assert check_grad(lambda v: fun(v)[0], lambda v: fun(v)[1], x) < 1e-3  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Strength uncertainty in the season simulator
# ---------------------------------------------------------------------------
def test_strength_sd_zero_is_unchanged_and_positive_sd_softens_certainty() -> None:
    from app.domain.models import LeagueRules, Tiebreaker, Zone
    from app.simulations.domestic import simulate_league

    as_of = T0
    recs = [MatchRecord(i, T0 + timedelta(days=i + 1), "TEST", 2026, h, a, None, None)
            for i, (h, a) in enumerate(permutations(range(1, 7), 2))]  # fmt: skip
    rules = LeagueRules("TEST", 2026, 6, 3, 1, (Tiebreaker.POINTS, Tiebreaker.GOAL_DIFFERENCE,
                        Tiebreaker.PLAYOFF), zones=(Zone("champion", "C", 1, 1),))  # fmt: skip
    s = {1: 0.6} | {t: 0.0 for t in range(2, 7)}
    model = PoissonModel(PoissonParams(), as_of, 0.3, 0.2, s, dict(s), 100, True)
    base = simulate_league(recs, "TEST", 2026, model, rules, as_of, n_sims=3000, seed=4)
    same = simulate_league(
        recs, "TEST", 2026, model, rules, as_of, n_sims=3000, seed=4, strength_sd=0.0
    )
    assert np.array_equal(base.position_probs, same.position_probs)
    noisy = simulate_league(
        recs, "TEST", 2026, model, rules, as_of, n_sims=3000, seed=4, strength_sd=0.3
    )
    assert np.allclose(noisy.position_probs.sum(0), 1) and np.allclose(
        noisy.position_probs.sum(1), 1
    )
    assert noisy.title_probs[1] < base.title_probs[1]  # less certain about the favourite
