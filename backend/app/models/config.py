"""
The production model configuration: the ONE place forecasts take settings from.

Chosen by time-ordered backtesting (docs/backtest-report.md, decision OD-005):
tuned on 2024/25, tested once on 2025/26 + 2026/27 to date.  Change these only
with a new backtest, and bump MODEL_VERSION when you do.
"""

from __future__ import annotations

from app.models.poisson import PoissonParams

MODEL_NAME = "poisson-montecarlo"
MODEL_VERSION = "0.2.0"

# Match model: independent Poisson; group priors for promoted / UCL-only clubs.
# Beat Elo significantly on the test period (log loss 0.9812 vs 0.9908); the
# Elo+Poisson blend did not beat Poisson alone on test data, so it is not used.
POISSON = PoissonParams(decay_per_day=0.0019, l2_penalty=4.0, group_priors=True)

# Season simulation: per-simulation uncertainty in club strength (log-goals sd).
# Chosen on 2024/25; on 2025/26 it improved final-position RPS and top-4 Brier,
# was slightly worse for title/relegation, i.e. roughly neutral overall, while
# reducing overconfidence in the 70-90% range.  Domestic leagues only for now.
STRENGTH_SD = 0.15
