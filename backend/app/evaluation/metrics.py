"""
Scoring rules for probabilistic forecasts of match outcomes.

Outcomes are encoded 0 = home win, 1 = draw, 2 = away win; probabilities are
an (n, 3) array in the same order.  Lower is better for every score here
except accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Probs = NDArray[np.float64]
Outcomes = NDArray[np.int64]

_EPS = 1e-15


def _check(p: Probs, y: Outcomes) -> None:
    if p.ndim != 2 or p.shape[1] != 3 or len(p) != len(y):
        raise ValueError(f"Expected (n, 3) probabilities for n outcomes, got {p.shape} / {y.shape}")
    if len(y) == 0:
        raise ValueError("No outcomes to score")
    if not np.allclose(p.sum(axis=1), 1.0, atol=1e-6) or (p < -1e-12).any():
        raise ValueError("Each row must be a probability distribution")


def log_loss(p: Probs, y: Outcomes) -> float:
    """Mean negative log-probability of what happened (heavily punishes confident misses)."""
    _check(p, y)
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], _EPS, 1.0))))


def brier(p: Probs, y: Outcomes) -> float:
    """Mean squared error over the three outcomes (0 = perfect, 2 = worst)."""
    _check(p, y)
    return float(np.mean(np.sum((p - np.eye(3)[y]) ** 2, axis=1)))


def rps(p: Probs, y: Outcomes) -> float:
    """Ranked probability score: respects the ordering home > draw > away, so
    predicting a draw when the home side wins is 'less wrong' than predicting an away win."""
    _check(p, y)
    cum_p = np.cumsum(p, axis=1)[:, :2]
    cum_y = np.cumsum(np.eye(3)[y], axis=1)[:, :2]
    return float(np.mean(np.sum((cum_p - cum_y) ** 2, axis=1) / 2))


def accuracy(p: Probs, y: Outcomes) -> float:
    """Share of matches where the most likely outcome happened (incomplete on its own)."""
    _check(p, y)
    return float(np.mean(np.argmax(p, axis=1) == y))


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float


def calibration(p: Probs, y: Outcomes, n_bins: int = 10) -> list[CalibrationBin]:
    """Reliability table over all (match, outcome) probabilities pooled together.

    A well-calibrated model has observed_rate ≈ mean_predicted in every bin.
    """
    _check(p, y)
    probs = p.ravel()
    hits = np.eye(3)[y].ravel()
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    which = np.clip(np.digitize(probs, edges[1:-1]), 0, n_bins - 1)
    out = []
    for b in range(n_bins):
        mask = which == b
        if mask.any():
            out.append(
                CalibrationBin(
                    float(edges[b]), float(edges[b + 1]), int(mask.sum()),
                    float(probs[mask].mean()), float(hits[mask].mean()),
                )
            )  # fmt: skip
    return out


def expected_calibration_error(p: Probs, y: Outcomes, n_bins: int = 10) -> float:
    """Count-weighted mean |observed − predicted| across calibration bins."""
    bins = calibration(p, y, n_bins)
    total = sum(b.count for b in bins)
    return float(sum(b.count * abs(b.observed_rate - b.mean_predicted) for b in bins) / total)


def summary(p: Probs, y: Outcomes) -> dict[str, float]:
    return {
        "n": float(len(y)),
        "log_loss": log_loss(p, y),
        "brier": brier(p, y),
        "rps": rps(p, y),
        "accuracy": accuracy(p, y),
        "ece": expected_calibration_error(p, y),
    }
