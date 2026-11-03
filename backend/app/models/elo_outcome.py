"""
Turn an Elo rating difference into home/draw/away probabilities.

Elo alone gives an expected *score*, not a draw probability.  An ordered
logistic model maps the pre-match rating difference d (incl. home advantage,
in units of 100 Elo points) to three outcomes:

    P(away)            = σ(c1 − β·d)
    P(away or draw)    = σ(c2 − β·d),   c1 < c2
    P(home)            = 1 − σ(c2 − β·d)

β, c1, c2 are fitted by maximum likelihood on pre-match ratings of matches
before ``as_of`` (the ratings themselves come from ``compute_elo`` with the
same cutoff, so there is no leakage).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_expit

from app.models.data import MatchRecord, played_before
from app.models.elo import EloResult


@dataclass(frozen=True)
class EloOutcomeModel:
    beta: float
    c1: float
    c2: float
    matches_used: int

    def probabilities(self, rating_diff: float) -> tuple[float, float, float]:
        """(P home, P draw, P away) for a rating difference incl. home advantage."""
        d = rating_diff / 100.0
        p_away = float(expit(self.c1 - self.beta * d))
        p_away_or_draw = float(expit(self.c2 - self.beta * d))
        return (1.0 - p_away_or_draw, p_away_or_draw - p_away, p_away)


def rating_diff(elo: EloResult, home: int, away: int, *, neutral: bool = False) -> float:
    return elo.rating(home) - elo.rating(away) + (0.0 if neutral else elo.params.home_advantage)


def fit_elo_outcomes(
    records: Sequence[MatchRecord],
    elo: EloResult,
    as_of: datetime,
    *,
    skip_first: int = 0,
) -> EloOutcomeModel:
    """Fit on matches before ``as_of``.  ``skip_first`` drops early burn-in matches
    whose pre-match ratings were still mostly the starting values."""
    if elo.as_of > as_of:
        raise ValueError("Elo ratings were computed with a later cutoff than as_of (leakage)")
    matches = played_before(records, as_of)[skip_first:]
    matches = [m for m in matches if m.fixture_id in elo.pre_match]
    if len(matches) < 50:
        raise ValueError(f"Only {len(matches)} matches to fit Elo outcome model")

    adv = elo.params.home_advantage
    d = np.array(
        [
            (elo.pre_match[m.fixture_id][0] - elo.pre_match[m.fixture_id][1]
             + (0.0 if m.neutral else adv)) / 100.0
            for m in matches
        ]
    )  # fmt: skip
    y = np.array(
        [0 if m.home_goals < m.away_goals else 1 if m.home_goals == m.away_goals else 2  # type: ignore[operator]
         for m in matches]
    )  # fmt: skip

    def nll(x: np.ndarray) -> float:
        beta, c1, gap = x
        c2 = c1 + np.exp(gap)  # keeps c1 < c2
        a = c1 - beta * d
        b = c2 - beta * d
        p_away = log_expit(a)
        p_home = log_expit(-b)
        # log(σ(b) − σ(a)) computed stably
        p_draw = np.log(np.clip(expit(b) - expit(a), 1e-12, None))
        ll = np.where(y == 0, p_away, np.where(y == 1, p_draw, p_home))
        return -float(ll.sum())

    res = minimize(nll, np.array([0.5, -1.0, 0.0]), method="Nelder-Mead",
                   options={"xatol": 1e-8, "fatol": 1e-8, "maxiter": 5000})  # fmt: skip
    beta, c1, gap = res.x
    return EloOutcomeModel(float(beta), float(c1), float(c1 + np.exp(gap)), len(matches))
