"""
Milestone 6 — walk-forward backtest of the match-outcome models.

  burn-in  : 2023/24             (training data only, never scored)
  tuning   : 2024-07-01 .. 2025-07-01   parameters are chosen here (log loss)
  test     : 2025-07-01 .. --test-end   chosen settings scored ONCE, never tuned on

Writes docs/backtest-report.md and backend/reports/backtest.json.

Usage (from backend/):  .venv/Scripts/python scripts/backtest.py [--quick]
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

import numpy as np

from app.database.connection import connect
from app.database.forecasts import git_commit, save_backtest
from app.evaluation.backtest import (
    BacktestResult,
    base_rates,
    elo_model,
    poisson_model,
    walk_forward,
)
from app.evaluation.metrics import calibration, log_loss, summary
from app.models import config
from app.models.data import load_match_records
from app.models.elo import EloParams
from app.models.poisson import PoissonParams

ROOT = Path(__file__).resolve().parents[2]
TUNE_START = datetime(2024, 7, 1, tzinfo=UTC)
TEST_START = datetime(2025, 7, 1, tzinfo=UTC)
COMPS = ["EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A", "UCL"]


def paired_bootstrap(
    y: np.ndarray, pa: np.ndarray, pb: np.ndarray, n: int = 2000
) -> tuple[float, float, float]:
    """Mean log-loss difference (a - b) with a 95% bootstrap interval. Negative = a better."""
    la = -np.log(np.clip(pa[np.arange(len(y)), y], 1e-15, 1))
    lb = -np.log(np.clip(pb[np.arange(len(y)), y], 1e-15, 1))
    d = la - lb
    rng = np.random.default_rng(0)
    boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)]
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def blend(p_elo: np.ndarray, p_poi: np.ndarray, w: float) -> np.ndarray:
    return w * p_elo + (1 - w) * p_poi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small grid (smoke test)")
    ap.add_argument("--test-end", default=None, help="ISO date; default: now")
    args = ap.parse_args()
    test_end = (datetime.fromisoformat(args.test_end).replace(tzinfo=UTC) if args.test_end
                else datetime.now(tz=UTC))  # fmt: skip

    with connect() as conn:
        recs = load_match_records(conn)

    # ---------------- grids ----------------
    if args.quick:
        poi_grid = [PoissonParams(), PoissonParams(group_priors=True)]
        elo_grid = [EloParams()]
    else:
        poi_grid = [
            PoissonParams(decay_per_day=d, l2_penalty=l2, group_priors=g)
            for d, l2, g in itertools.product(
                (0.0, 0.001, 0.0019, 0.003, 0.005), (0.5, 1.0, 2.0, 4.0, 8.0), (False, True)
            )
        ]
        elo_grid = [
            EloParams(k=k, home_advantage=h, season_regression=r)
            for k, h, r in itertools.product((15, 20, 25, 30, 40), (40, 65, 90), (0.0, 0.2, 0.4))
        ]

    # ---------------- tuning ----------------
    t0 = time.time()
    models: dict[str, Any] = {f"poisson#{i}": poisson_model(p) for i, p in enumerate(poi_grid)}
    models |= {f"elo#{i}": elo_model(p) for i, p in enumerate(elo_grid)}
    tune = walk_forward(recs, models, TUNE_START, TEST_START)
    y_t = tune.y()
    poi_scores = [(log_loss(tune.p(f"poisson#{i}"), y_t), i) for i in range(len(poi_grid))]
    elo_scores = [(log_loss(tune.p(f"elo#{i}"), y_t), i) for i in range(len(elo_grid))]
    best_poi = poi_grid[min(poi_scores)[1]]
    best_elo = elo_grid[min(elo_scores)[1]]
    p_e, p_p = tune.p(f"elo#{min(elo_scores)[1]}"), tune.p(f"poisson#{min(poi_scores)[1]}")
    blend_scores = [(log_loss(blend(p_e, p_p, w), y_t), w) for w in np.linspace(0, 1, 11)]
    best_w = float(min(blend_scores)[1])
    print(f"tuning: {len(y_t)} matches, {tune.cutoffs} weekly refits, {time.time() - t0:.0f}s")
    print(f"  best Poisson {best_poi}  log loss {min(poi_scores)[0]:.4f}")
    print(f"  best Elo     {best_elo}  log loss {min(elo_scores)[0]:.4f}")
    print(f"  blend weight on Elo: {best_w:.1f}")

    # ---------------- test (scored once) ----------------
    t0 = time.time()
    test_models = {
        "base rates": base_rates(),
        "Elo (default)": elo_model(EloParams()),
        "Poisson (default)": poisson_model(PoissonParams()),
        "Elo (tuned)": elo_model(best_elo),
        "Poisson (tuned)": poisson_model(best_poi),
    }
    test = walk_forward(recs, test_models, TEST_START, test_end)
    test.probs["Blend (tuned)"] = [
        blend(e, p, best_w)
        for e, p in zip(test.probs["Elo (tuned)"], test.probs["Poisson (tuned)"], strict=True)
    ]
    y = test.y()
    print(f"test: {len(y)} matches, {test.cutoffs} weekly refits, {time.time() - t0:.0f}s")

    write_report(test, y, best_poi, best_elo, best_w, poi_scores, elo_scores, blend_scores,
                 poi_grid, elo_grid, len(y_t), test_end)  # fmt: skip


def write_report(
    test: BacktestResult, y: np.ndarray, best_poi: PoissonParams, best_elo: EloParams, best_w: float,
    poi_scores: list[tuple[float, int]], elo_scores: list[tuple[float, int]],
    blend_scores: list[tuple[float, float]], poi_grid: list[PoissonParams],
    elo_grid: list[EloParams], n_tune: int, test_end: datetime,
) -> None:  # fmt: skip
    names = list(test.probs)
    overall = {n: summary(test.p(n), y) for n in names}
    by_comp = {
        c: {n: log_loss(test.p(n)[m], y[m]) for n in names}
        for c in COMPS
        if (m := test.mask(c)).sum() > 0
    }
    counts = {c: int(test.mask(c).sum()) for c in COMPS}
    best = min(names, key=lambda n: overall[n]["log_loss"])
    comparisons = {
        f"{best} vs {other}": paired_bootstrap(y, test.p(best), test.p(other))
        for other in names
        if other != best
    }
    cal = calibration(test.p(best), y)

    lines = [
        "# Backtest Report (Milestone 6)",
        "",
        f"> Generated {datetime.now(tz=UTC):%Y-%m-%d %H:%M} UTC by `backend/scripts/backtest.py`.",
        "> Walk-forward: models are refit every week using only matches that kicked off earlier,",
        "> then predict that week. Outcome = result after 90 minutes. Lower is better for all scores",
        "> except accuracy.",
        "",
        "## Design",
        "",
        "| Period | Dates | Use |",
        "|---|---|---|",
        "| Burn-in | 2023/24 | training data only, never scored |",
        f"| Tuning | 2024-07-01 → 2025-07-01 ({n_tune} matches) | parameters chosen by log loss |",
        f"| **Test** | 2025-07-01 → {test_end:%Y-%m-%d} ({len(y)} matches) | chosen settings scored once |",
        "",
        "## Chosen settings (from the tuning period only)",
        "",
        f"- **Poisson:** decay {best_poi.decay_per_day}/day, L2 {best_poi.l2_penalty}, "
        f"group priors {'on' if best_poi.group_priors else 'off'} "
        f"(tuning log loss {min(poi_scores)[0]:.4f}; {len(poi_grid)} configurations tried)",
        f"- **Elo:** K {best_elo.k}, home advantage {best_elo.home_advantage}, season regression "
        f"{best_elo.season_regression} (tuning log loss {min(elo_scores)[0]:.4f}; "
        f"{len(elo_grid)} configurations tried)",
        f"- **Blend:** {best_w:.1f} × Elo + {1 - best_w:.1f} × Poisson "
        f"(tuning log loss {min(blend_scores)[0]:.4f})",
        "",
        "## Test-period results",
        "",
        "| Model | Log loss | Brier | RPS | Accuracy | Calibration error (ECE) |",
        "|---|---|---|---|---|---|",
    ]
    for n in sorted(names, key=lambda n: overall[n]["log_loss"]):
        s = overall[n]
        lines.append(f"| {n} | {s['log_loss']:.4f} | {s['brier']:.4f} | {s['rps']:.4f} | "
                     f"{s['accuracy']:.1%} | {s['ece']:.4f} |")  # fmt: skip
    lines += [
        "",
        f"### Is **{best}** really better? (paired bootstrap, test period)",
        "",
        "Mean log-loss difference per match; negative = the best model is better. If the 95%",
        "interval includes 0, the difference is not distinguishable from noise.",
        "",
        "| Comparison | Mean difference | 95% interval |",
        "|---|---|---|",
    ]
    for k, (d, lo, hi) in comparisons.items():
        verdict = "" if lo < 0 < hi else (" ✓" if hi < 0 else " ✗")
        lines.append(f"| {k} | {d:+.4f} | [{lo:+.4f}, {hi:+.4f}]{verdict} |")
    lines += [
        "",
        "### Log loss by competition (test period)",
        "",
        "| Competition | Matches | " + " | ".join(names) + " |",
        "|---|---|" + "---|" * len(names),
    ]
    for c, row in by_comp.items():
        lines.append(f"| {c} | {counts[c]} | " + " | ".join(f"{row[n]:.4f}" for n in names) + " |")
    lines += [
        "",
        f"### Calibration of {best} (test period)",
        "",
        "All home/draw/away probabilities pooled. Well calibrated means 'Observed' ≈ 'Predicted'.",
        "",
        "| Predicted range | Count | Predicted (mean) | Observed |",
        "|---|---|---|---|",
    ]
    for b in cal:
        lines.append(f"| {b.lower:.0%}–{b.upper:.0%} | {b.count} | {b.mean_predicted:.1%} | "
                     f"{b.observed_rate:.1%} |")  # fmt: skip
    lines += [
        "",
        "## Caveats",
        "",
        "- One test window (~1.3 seasons). Results can shift with more data.",
        "- Tuning used a single season; the grid is coarse.",
        "- Match-level results say nothing yet about **season-level** calibration "
        "(title/relegation probabilities). That is evaluated separately.",
        "",
    ]
    (ROOT / "docs" / "backtest-report.md").write_text("\n".join(lines), encoding="utf-8")
    out = ROOT / "backend" / "reports"
    out.mkdir(exist_ok=True)
    (out / "backtest.json").write_text(json.dumps({
        "generated": datetime.now(tz=UTC).isoformat(),
        "chosen": {"poisson": best_poi.to_dict(), "elo": best_elo.to_dict(), "blend_elo_weight": best_w},
        "test_overall": overall, "test_by_competition": by_comp, "comparisons": comparisons,
        "calibration": [b.__dict__ for b in cal],
    }, indent=2), encoding="utf-8")  # fmt: skip
    with connect() as conn:
        run_id = save_backtest(
            conn, kind="match", model_name=config.MODEL_NAME, model_version=config.MODEL_VERSION,
            params={"poisson": best_poi.to_dict(), "elo": best_elo.to_dict(),
                    "blend_elo_weight": best_w},
            tuning_window={"start": TUNE_START.isoformat(), "end": TEST_START.isoformat()},
            test_window={"start": TEST_START.isoformat(), "end": test_end.isoformat()},
            metrics={"overall": overall, "by_competition": by_comp, "comparisons": comparisons,
                     "calibration": [b.__dict__ for b in cal], "n_test": len(y)},
            code_version=git_commit(),
        )  # fmt: skip
    print("\n".join(lines[lines.index("## Test-period results") :]))
    print(f"\nStored as backtest run #{run_id}")


if __name__ == "__main__":
    main()
