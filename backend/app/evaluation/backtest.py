"""
Walk-forward (time-ordered) backtesting of match-outcome models.

For each weekly cutoff t in [start, end):
    fit every model on matches that kicked off before t   (played_before guard)
    predict the matches that kick off in [t, t + 7 days)
So every prediction uses only information that existed at the time.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from numpy.typing import NDArray

from app.models.data import MatchRecord, played_before
from app.models.elo import EloParams, compute_elo
from app.models.elo_outcome import fit_elo_outcomes, rating_diff
from app.models.poisson import PoissonParams, fit_poisson, outcome_probabilities

Probs = NDArray[np.float64]
# A fitted predictor maps the matches of one week to an (n, 3) array of H/D/A probabilities.
Predictor = Callable[[Sequence[MatchRecord]], Probs]
# A model factory fits on everything before ``as_of`` and returns a predictor.
ModelFactory = Callable[[Sequence[MatchRecord], datetime], Predictor]


def outcome(m: MatchRecord) -> int:
    assert m.home_goals is not None and m.away_goals is not None
    return 0 if m.home_goals > m.away_goals else 1 if m.home_goals == m.away_goals else 2


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------
def base_rates() -> ModelFactory:
    """Always predict the historical home/draw/away frequencies."""

    def fit(records: Sequence[MatchRecord], as_of: datetime) -> Predictor:
        past = played_before(records, as_of)
        freq = np.bincount([outcome(m) for m in past], minlength=3) / len(past)
        return lambda ms: np.tile(freq, (len(ms), 1))

    return fit


def elo_model(params: EloParams, burn_in: int = 1000) -> ModelFactory:
    def fit(records: Sequence[MatchRecord], as_of: datetime) -> Predictor:
        elo = compute_elo(records, as_of, params)
        skip = min(burn_in, max(0, elo.matches_used - 300))  # keep >= 300 for the fit
        mapping = fit_elo_outcomes(records, elo, as_of, skip_first=skip)

        def predict(ms: Sequence[MatchRecord]) -> Probs:
            return np.array(
                [
                    mapping.probabilities(
                        rating_diff(elo, m.home_team_id, m.away_team_id, neutral=m.neutral)
                    )
                    for m in ms
                ]
            )

        return predict

    return fit


def poisson_model(params: PoissonParams) -> ModelFactory:
    def fit(records: Sequence[MatchRecord], as_of: datetime) -> Predictor:
        model = fit_poisson(records, as_of, params)

        def predict(ms: Sequence[MatchRecord]) -> Probs:
            return np.array(
                [
                    outcome_probabilities(
                        model.score_matrix(
                            m.home_team_id,
                            m.away_team_id,
                            neutral=m.neutral,
                            competition=m.competition,
                        )
                    )  # fmt: skip
                    for m in ms
                ]
            )

        return predict

    return fit


# ---------------------------------------------------------------------------
# Walk-forward loop
# ---------------------------------------------------------------------------
@dataclass
class BacktestResult:
    matches: list[MatchRecord] = field(default_factory=list)
    outcomes: list[int] = field(default_factory=list)
    probs: dict[str, list[Probs]] = field(default_factory=dict)
    cutoffs: int = 0

    def y(self) -> NDArray[np.int64]:
        return np.array(self.outcomes, dtype=np.int64)

    def p(self, name: str) -> Probs:
        return np.vstack(self.probs[name])

    def mask(
        self, competition: str | None = None, since: datetime | None = None
    ) -> NDArray[np.bool_]:
        return np.array(
            [
                (competition is None or m.competition == competition)
                and (since is None or m.kickoff_utc >= since)
                for m in self.matches
            ]
        )


def walk_forward(
    records: Sequence[MatchRecord],
    models: dict[str, ModelFactory],
    start: datetime,
    end: datetime,
    *,
    step_days: int = 7,
) -> BacktestResult:
    """Predict every played match with kickoff in [start, end), refitting weekly."""
    played = sorted(
        (m for m in records if m.is_played), key=lambda m: (m.kickoff_utc, m.fixture_id)
    )
    result = BacktestResult(probs={name: [] for name in models})
    t = start
    while t < end:
        t_next = min(t + timedelta(days=step_days), end)
        week = [m for m in played if t <= m.kickoff_utc < t_next]
        if week:
            result.cutoffs += 1
            result.matches += week
            result.outcomes += [outcome(m) for m in week]
            for name, factory in models.items():
                predictor = factory(records, t)  # fitted strictly before t
                p = predictor(week)
                if p.shape != (len(week), 3):
                    raise ValueError(f"{name} returned shape {p.shape}")
                result.probs[name].append(p)
        t = t_next
    return result
