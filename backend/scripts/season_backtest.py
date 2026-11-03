"""
Milestone 6 — season-level backtest: are title / top-4 / relegation / final-position
probabilities calibrated, and how much team-strength uncertainty should the
simulator use?

For each completed season and each cutoff date (1 Oct, 15 Nov, 15 Jan, 15 Mar):
  fit the model on matches before the cutoff, simulate the rest of the season,
  and score the forecast against the actual final table (computed with the
  league's rules from the real results).

  tuning: 2024/25 cutoffs   -> choose strength_sd
  test  : 2025/26 cutoffs   -> scored once

Appends a section to docs/backtest-report.md and writes backend/reports/season_backtest.json.
Usage (from backend/):  .venv/Scripts/python scripts/season_backtest.py
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

import numpy as np

from app.database.connection import connect
from app.database.forecasts import git_commit, save_backtest
from app.models import config
from app.models.data import MatchRecord, load_match_records
from app.models.poisson import PoissonParams, fit_poisson
from app.simulations.domestic import SeasonForecast, simulate_league
from app.simulations.rules import load_rules
from app.simulations.table import rank_teams

ROOT = Path(__file__).resolve().parents[2]
LEAGUES = ["EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A"]
ZONES = ["champion", "champions_league", "relegation"]
SDS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
N_SIMS = 4000
# Match-model settings chosen by scripts/backtest.py (tuning period only).
CHOSEN_POISSON = PoissonParams(decay_per_day=0.0019, l2_penalty=4.0, group_priors=True)


def cutoffs(season: int) -> list[datetime]:
    return [datetime(season, 10, 1, tzinfo=UTC), datetime(season, 11, 15, tzinfo=UTC),
            datetime(season + 1, 1, 15, tzinfo=UTC), datetime(season + 1, 3, 15, tzinfo=UTC)]  # fmt: skip


def actual_positions(recs: list[MatchRecord], comp: str, season: int) -> dict[int, int]:
    res = [(m.home_team_id, m.away_team_id, int(m.home_goals or 0), int(m.away_goals or 0))
           for m in recs if m.competition == comp and m.season_year == season and m.is_played]  # fmt: skip
    rules = replace(load_rules(comp, 2026), season_start_year=season)
    teams = sorted({t for r in res for t in r[:2]})
    orders = {tuple(rank_teams(teams, res, rules, np.random.default_rng(s))) for s in range(5)}
    if len(orders) != 1:
        print(f"  warning: {comp} {season} final table needed a random tiebreak")
    return {t: i + 1 for i, t in enumerate(orders.pop())}


def score(f: SeasonForecast, actual: dict[int, int]) -> dict[str, list[float]]:
    """Per-team scores: position RPS, and (prob, outcome) pairs per zone."""
    n = len(f.team_ids)
    rules = load_rules(f.competition, 2026)
    out: dict[str, list[float]] = {
        "rps": [],
        **{f"{z}_p": [] for z in ZONES},
        **{f"{z}_y": [] for z in ZONES},
    }
    for i, t in enumerate(f.team_ids):
        cum = np.cumsum(f.position_probs[i])[:-1]
        step = (np.arange(1, n) >= actual[t]).astype(float)
        out["rps"].append(float(np.sum((cum - step) ** 2) / (n - 1)))
        for z in ZONES:
            zone = rules.zone(z)
            assert zone is not None
            out[f"{z}_p"].append(f.zone_probs[z][t])
            out[f"{z}_y"].append(1.0 if zone.contains(actual[t]) else 0.0)
    return out


def evaluate(
    recs: list[MatchRecord], season: int, sds: list[float]
) -> dict[float, dict[str, list[float]]]:
    acc: dict[float, dict[str, list[float]]] = {sd: {} for sd in sds}
    actual = {c: actual_positions(recs, c, season) for c in LEAGUES}
    for cut in cutoffs(season):
        model = fit_poisson(recs, cut, CHOSEN_POISSON)
        for comp in LEAGUES:
            rules = replace(load_rules(comp, 2026), season_start_year=season)
            for sd in sds:
                f = simulate_league(recs, comp, season, model, rules, cut, n_sims=N_SIMS,
                                    seed=1, strength_sd=sd)  # fmt: skip
                for k, v in score(f, actual[comp]).items():
                    acc[sd].setdefault(k, []).extend(v)
    return acc


def summarise(acc: dict[str, list[float]]) -> dict[str, float]:
    s = {"position_rps": float(np.mean(acc["rps"]))}
    for z in ZONES:
        p, y = np.array(acc[f"{z}_p"]), np.array(acc[f"{z}_y"])
        s[f"{z}_brier"] = float(np.mean((p - y) ** 2))
        pc = np.clip(p, 1e-3, 1 - 1e-3)
        s[f"{z}_logloss"] = float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))
    s["zone_brier_total"] = sum(s[f"{z}_brier"] for z in ZONES)
    return s


def reliability(acc: dict[str, list[float]]) -> list[tuple[str, int, float, float]]:
    """Pooled zone probabilities in bins: (range, count, mean predicted, observed rate)."""
    p = np.concatenate([acc[f"{z}_p"] for z in ZONES])
    y = np.concatenate([acc[f"{z}_y"] for z in ZONES])
    edges = [0, 0.02, 0.1, 0.3, 0.5, 0.7, 0.9, 0.98, 1.0001]
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rows.append(
                (f"{lo:.0%}–{min(hi, 1):.0%}", int(m.sum()), float(p[m].mean()), float(y[m].mean()))
            )
    return rows


def main() -> None:
    with connect() as conn:
        recs = load_match_records(conn)
    t0 = time.time()
    tune = {sd: summarise(a) for sd, a in evaluate(recs, 2024, SDS).items()}
    best_sd = min(SDS, key=lambda sd: tune[sd]["position_rps"] + tune[sd]["zone_brier_total"])
    print(f"tuning (2024/25): {time.time() - t0:.0f}s; chosen strength_sd = {best_sd}")
    t0 = time.time()
    test_raw = evaluate(recs, 2025, sorted({0.0, best_sd}))
    test = {sd: summarise(a) for sd, a in test_raw.items()}
    print(f"test (2025/26): {time.time() - t0:.0f}s")

    lines = [
        "",
        "## Season-level backtest (title / top 4 / relegation / final position)",
        "",
        f"> Generated {datetime.now(tz=UTC):%Y-%m-%d %H:%M} UTC by `backend/scripts/season_backtest.py`.",
        "> Forecasts made on 1 Oct, 15 Nov, 15 Jan and 15 Mar using only data before that date,",
        f"> {N_SIMS} simulations each, scored against the actual final tables (computed from the real",
        "> results with each league's tiebreakers). Model: Poisson with the tuned settings.",
        "> `strength_sd` adds uncertainty about how good each club really is.",
        "",
        "### Tuning (2024/25): choosing `strength_sd`",
        "",
        "| strength_sd | Position RPS | Champion Brier | Top-4 Brier | Relegation Brier | Sum of zone Briers |",
        "|---|---|---|---|---|---|",
    ]
    for sd in SDS:
        s = tune[sd]
        lines.append(f"| {sd:.2f}{' ←' if sd == best_sd else ''} | {s['position_rps']:.5f} | "
                     f"{s['champion_brier']:.5f} | {s['champions_league_brier']:.5f} | "
                     f"{s['relegation_brier']:.5f} | {s['zone_brier_total']:.5f} |")  # fmt: skip
    lines += [
        "",
        "### Test (2025/26)",
        "",
        "| strength_sd | Position RPS | Champion Brier | Top-4 Brier | Relegation Brier | Sum of zone Briers |",
        "|---|---|---|---|---|---|",
    ]
    for sd, s in test.items():
        lines.append(f"| {sd:.2f} | {s['position_rps']:.5f} | {s['champion_brier']:.5f} | "
                     f"{s['champions_league_brier']:.5f} | {s['relegation_brier']:.5f} | "
                     f"{s['zone_brier_total']:.5f} |")  # fmt: skip
    for sd in sorted(test):
        lines += [
            "",
            f"### Reliability of zone probabilities, 2025/26, strength_sd = {sd:.2f}",
            "",
            "Title, top-4 and relegation probabilities pooled (4 leagues × 4 dates).",
            "",
            "| Predicted range | Count | Predicted (mean) | Observed |",
            "|---|---|---|---|",
        ]
        for rng_label, n, pm, ob in reliability(test_raw[sd]):
            lines.append(f"| {rng_label} | {n} | {pm:.1%} | {ob:.1%} |")
    lines += [
        "",
        "Caveat: a season-level sample is small (each season gives 4 leagues × 4 dates, and outcomes",
        "within a season are strongly correlated), so these numbers are indicative, not precise.",
        "",
    ]
    report = ROOT / "docs" / "backtest-report.md"
    text = report.read_text(encoding="utf-8")
    marker = "\n## Season-level backtest"
    if marker in text:
        text = text[: text.index(marker)]
    report.write_text(text.rstrip("\n") + "\n" + "\n".join(lines), encoding="utf-8")
    (ROOT / "backend" / "reports" / "season_backtest.json").write_text(
        json.dumps({"tuning": tune, "test": test, "chosen_strength_sd": best_sd}, indent=2),
        encoding="utf-8",
    )
    with connect() as conn:
        run_id = save_backtest(
            conn, kind="season", model_name=config.MODEL_NAME, model_version=config.MODEL_VERSION,
            params={"poisson": CHOSEN_POISSON.to_dict(), "strength_sd_grid": SDS,
                    "chosen_strength_sd": best_sd, "n_sims": N_SIMS},
            tuning_window={"season": "2024/25", "cutoffs": [c.isoformat() for c in cutoffs(2024)]},
            test_window={"season": "2025/26", "cutoffs": [c.isoformat() for c in cutoffs(2025)]},
            metrics={"tuning": tune, "test": test,
                     "reliability": {str(sd): reliability(a) for sd, a in test_raw.items()}},
            code_version=git_commit(),
        )  # fmt: skip
    print("\n".join(lines))
    print(f"\nStored as backtest run #{run_id}")


if __name__ == "__main__":
    main()
