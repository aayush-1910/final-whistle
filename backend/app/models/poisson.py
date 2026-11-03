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
from dataclasses import asdict, dataclass, field
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
    # Shrink promoted clubs and UCL-only clubs toward LEARNED group means instead
    # of toward an average club (see fit_poisson).  Unknown clubs at prediction
    # time then start from their group's mean.
    group_priors: bool = False

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
    # Learned (attack, defence) means for "promoted" and "ucl_only" clubs, if enabled.
    priors: dict[str, tuple[float, float]] = field(default_factory=dict)
    groups: dict[int, str] = field(default_factory=dict)

    def knows(self, team_id: int) -> bool:
        return team_id in self.attack

    def effects(self, team_id: int, competition: str | None = None) -> tuple[float, float]:
        """(attack, defence) of a club.  An unknown club is average, or - with group
        priors - a typical newcomer: UCL-only club in the UCL, promoted club elsewhere."""
        if team_id in self.attack:
            return self.attack[team_id], self.defence[team_id]
        if self.priors and competition is not None:
            return self.priors["ucl_only" if competition == "UCL" else "promoted"]
        return 0.0, 0.0

    def expected_goals(
        self,
        home_team_id: int,
        away_team_id: int,
        *,
        neutral: bool = False,
        competition: str | None = None,
    ) -> tuple[float, float]:
        """(λ_home, λ_away).  See :meth:`effects` for clubs the model has not seen."""
        ah, dh = self.effects(home_team_id, competition)
        aa, da = self.effects(away_team_id, competition)
        home = 0.0 if neutral else self.home_advantage
        return (
            float(np.exp(self.mu + home + ah - da)),
            float(np.exp(self.mu + aa - dh)),
        )

    def score_matrix(
        self,
        home_team_id: int,
        away_team_id: int,
        *,
        neutral: bool = False,
        competition: str | None = None,
    ) -> FloatArray:
        lh, la = self.expected_goals(
            home_team_id, away_team_id, neutral=neutral, competition=competition
        )
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

    groups = classify_teams(matches) if p.group_priors else {}
    # Shrink target per club: 0 = average, 1 = promoted-club mean, 2 = UCL-only-club mean.
    gi = np.array([GROUP_INDEX.get(groups.get(t, ""), 0) for t in teams])
    n_x = 2 + 2 * n + (4 if p.group_priors else 0)

    def unpack(x: FloatArray) -> tuple[float, float, FloatArray, FloatArray, FloatArray]:
        priors = np.zeros((3, 2))
        if p.group_priors:
            priors[1:] = x[2 + 2 * n :].reshape(2, 2)
        return x[0], x[1], x[2 : 2 + n], x[2 + n : 2 + 2 * n], priors

    def objective(x: FloatArray) -> tuple[float, FloatArray]:
        mu, home, att, dfn, priors = unpack(x)
        log_lh = mu + home * is_home + att[hi] - dfn[ai]
        log_la = mu + att[ai] - dfn[hi]
        lh, la = np.exp(log_lh), np.exp(log_la)
        nll = -float(np.sum(w * (hg * log_lh - lh + ag * log_la - la))) + const
        da, dd = att - priors[gi, 0], dfn - priors[gi, 1]  # deviation from shrink target
        nll += p.l2_penalty * float(np.sum(da**2) + np.sum(dd**2))

        rh = w * (hg - lh)  # d loglik / d log_lh
        ra = w * (ag - la)
        g = np.zeros_like(x)
        g[0] = -(rh.sum() + ra.sum())
        g[1] = -(rh * is_home).sum()
        g_att = -(np.bincount(hi, rh, n) + np.bincount(ai, ra, n)) + 2 * p.l2_penalty * da
        g_def = (np.bincount(ai, rh, n) + np.bincount(hi, ra, n)) + 2 * p.l2_penalty * dd
        g[2 : 2 + n], g[2 + n : 2 + 2 * n] = g_att, g_def
        if p.group_priors:
            for k in (1, 2):
                mask = gi == k
                g[2 + 2 * n + 2 * (k - 1)] = -2 * p.l2_penalty * da[mask].sum()
                g[2 + 2 * n + 2 * (k - 1) + 1] = -2 * p.l2_penalty * dd[mask].sum()
        return nll, g

    x0 = np.zeros(n_x)
    x0[0] = np.log(max((hg * w).sum() + (ag * w).sum(), 1e-9) / (2 * w.sum()))
    res = minimize(objective, x0, jac=True, method="L-BFGS-B", options={"maxiter": 3000})
    mu, home, att, dfn, priors = unpack(res.x)
    return PoissonModel(
        params=p,
        as_of=as_of,
        mu=float(mu),
        home_advantage=float(home),
        attack={t: float(att[i]) for t, i in idx.items()},
        defence={t: float(dfn[i]) for t, i in idx.items()},
        matches_used=len(matches),
        converged=bool(res.success),
        priors=(
            {
                "promoted": (float(priors[1, 0]), float(priors[1, 1])),
                "ucl_only": (float(priors[2, 0]), float(priors[2, 1])),
            }
            if p.group_priors
            else {}
        ),
        groups=groups,
    )


GROUP_INDEX = {"promoted": 1, "ucl_only": 2}
_DOMESTIC = frozenset({"EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A"})


def classify_teams(matches: Sequence[MatchRecord]) -> dict[int, str]:
    """Group clubs for the shrinkage prior, using only the given (past) matches.

    - ``ucl_only``: never played a domestic-league match in the data.
    - ``promoted``: first domestic match came in a later season than that
      league's first season in the data (so the club came up from below).
    - ``established``: everything else (present from the league's first season).
    """
    first_season: dict[str, int] = {}
    first_dom: dict[int, tuple[str, int]] = {}
    for m in matches:  # chronological
        if m.competition not in _DOMESTIC:
            continue
        first_season.setdefault(m.competition, m.season_year)
        for t in (m.home_team_id, m.away_team_id):
            first_dom.setdefault(t, (m.competition, m.season_year))
    out: dict[int, str] = {}
    for t in {t for m in matches for t in (m.home_team_id, m.away_team_id)}:
        if t not in first_dom:
            out[t] = "ucl_only"
        else:
            comp, season = first_dom[t]
            out[t] = "promoted" if season > first_season[comp] else "established"
    return out
