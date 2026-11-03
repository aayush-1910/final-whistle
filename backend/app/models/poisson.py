"""
Independent-Poisson goal model with time-decay weighting (Dixon-Coles style
weighting, WITHOUT the low-score correlation adjustment; that is only to be
added if backtests show it helps — README §7.2).

    log λ_home = μ + h·(not neutral) + attack[home] − defence[away]
    log λ_away = μ                   + attack[away] − defence[home]

Fitted by maximum weighted likelihood on matches before ``as_of`` only.
Each match is weighted exp(−ξ · days_before_as_of), so recent form counts
more.  An L2 penalty shrinks every team toward average; teams with few
matches (e.g. UCL-only clubs) therefore stay near average instead of being
judged on a handful of games.  It also makes the parameters identifiable.

One shared parameter set across all competitions (decision OD-004).
Defaults are PROVISIONAL until tuned by backtesting (Milestone 6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

from app.models.data import MatchRecord, played_before

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class PoissonParams:
    decay_per_day: float = 0.0019  # weight half-life ≈ 365 days
    l2_penalty: float = 2.0  # strength of shrinkage toward an average team
    max_goals: int = 10  # score grid is 0..max_goals for each side

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FitError(RuntimeError):
    pass


@dataclass
class PoissonModel:
    params: PoissonParams
    as_of: datetime
    mu: float
    home_advantage: float
    attack: dict[int, float]
    defence: dict[int, float]
    matches_used: int
    converged: bool

    def knows(self, team_id: int) -> bool:
        return team_id in self.attack

    def expected_goals(
        self, home_team_id: int, away_team_id: int, *, neutral: bool = False
    ) -> tuple[float, float]:
        """(λ_home, λ_away).  Unknown teams are treated as average (0 attack/defence)."""
        ah, dh = self.attack.get(home_team_id, 0.0), self.defence.get(home_team_id, 0.0)
        aa, da = self.attack.get(away_team_id, 0.0), self.defence.get(away_team_id, 0.0)
        home = 0.0 if neutral else self.home_advantage
        return (
            float(np.exp(self.mu + home + ah - da)),
            float(np.exp(self.mu + aa - dh)),
        )

    def score_matrix(
        self, home_team_id: int, away_team_id: int, *, neutral: bool = False
    ) -> FloatArray:
        lh, la = self.expected_goals(home_team_id, away_team_id, neutral=neutral)
        return score_matrix(lh, la, self.params.max_goals)


def score_matrix(lambda_home: float, lambda_away: float, max_goals: int) -> FloatArray:
    """P(home = i, away = j) for i, j in 0..max_goals, renormalised to sum to 1.

    The probability of more than ``max_goals`` for a side is negligible for
    realistic λ (<1e-6 at λ=3, max_goals=10) and is folded back by renormalising.
    """
    goals = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(goals, lambda_home), poisson.pmf(goals, lambda_away))
    total = m.sum()
    if not total > 0:
        raise ValueError("Degenerate score matrix")
    return np.asarray(m / total, dtype=np.float64)


def outcome_probabilities(matrix: FloatArray) -> tuple[float, float, float]:
    """(P home win, P draw, P away win) from a score matrix."""
    return (
        float(np.tril(matrix, -1).sum()),
        float(np.trace(matrix)),
        float(np.triu(matrix, 1).sum()),
    )


def fit_poisson(
    records: Sequence[MatchRecord], as_of: datetime, params: PoissonParams | None = None
) -> PoissonModel:
    """Fit on matches that kicked off strictly before ``as_of``."""
    p = params or PoissonParams()
    matches = played_before(records, as_of)
    if len(matches) < 50:
        raise FitError(f"Only {len(matches)} matches before {as_of:%Y-%m-%d}; need >= 50")

    teams = sorted({t for m in matches for t in (m.home_team_id, m.away_team_id)})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = np.array([idx[m.home_team_id] for m in matches])
    ai = np.array([idx[m.away_team_id] for m in matches])
    hg = np.array([m.home_goals for m in matches], dtype=np.float64)
    ag = np.array([m.away_goals for m in matches], dtype=np.float64)
    is_home = np.array([0.0 if m.neutral else 1.0 for m in matches])
    days = np.array([(as_of - m.kickoff_utc).total_seconds() / 86400.0 for m in matches])
    w = np.exp(-p.decay_per_day * days)
    const = float(np.sum(w * (gammaln(hg + 1) + gammaln(ag + 1))))

    def unpack(x: FloatArray) -> tuple[float, float, FloatArray, FloatArray]:
        return x[0], x[1], x[2 : 2 + n], x[2 + n :]

    def objective(x: FloatArray) -> tuple[float, FloatArray]:
        mu, home, att, dfn = unpack(x)
        log_lh = mu + home * is_home + att[hi] - dfn[ai]
        log_la = mu + att[ai] - dfn[hi]
        lh, la = np.exp(log_lh), np.exp(log_la)
        nll = -float(np.sum(w * (hg * log_lh - lh + ag * log_la - la))) + const
        nll += p.l2_penalty * float(np.sum(att**2) + np.sum(dfn**2))

        rh = w * (hg - lh)  # d loglik / d log_lh
        ra = w * (ag - la)
        g = np.zeros_like(x)
        g[0] = -(rh.sum() + ra.sum())
        g[1] = -(rh * is_home).sum()
        g_att = -(np.bincount(hi, rh, n) + np.bincount(ai, ra, n)) + 2 * p.l2_penalty * att
        g_def = (np.bincount(ai, rh, n) + np.bincount(hi, ra, n)) + 2 * p.l2_penalty * dfn
        g[2 : 2 + n], g[2 + n :] = g_att, g_def
        return nll, g

    x0 = np.zeros(2 + 2 * n)
    x0[0] = np.log(max((hg * w).sum() + (ag * w).sum(), 1e-9) / (2 * w.sum()))
    res = minimize(objective, x0, jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    mu, home, att, dfn = unpack(res.x)
    return PoissonModel(
        params=p,
        as_of=as_of,
        mu=float(mu),
        home_advantage=float(home),
        attack={t: float(att[i]) for t, i in idx.items()},
        defence={t: float(dfn[i]) for t, i in idx.items()},
        matches_used=len(matches),
        converged=bool(res.success),
    )
