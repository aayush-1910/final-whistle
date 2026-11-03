"""
Developer preview of the baseline models.  Prints to the terminal only:
nothing is stored and nothing reaches the dashboard.

  1. A sanity check: fit on data before a cutoff, score the matches after it.
  2. Current Elo top 10 per competition.
  3. Elo and Poisson probabilities for the next fixtures.

THE MODELS ARE NOT YET VALIDATED (Milestone 6).  Do not treat the output as a forecast.

Usage (from backend/):  .venv/Scripts/python scripts/preview_models.py [--next 5]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from app.database.connection import connect
from app.models.data import MatchRecord, load_match_records
from app.models.elo import compute_elo
from app.models.elo_outcome import fit_elo_outcomes, rating_diff
from app.models.poisson import fit_poisson, outcome_probabilities

BURN_IN = 1000  # early matches whose ratings were still mostly starting values


def outcome(m: MatchRecord) -> int:
    assert m.home_goals is not None and m.away_goals is not None
    return 0 if m.home_goals > m.away_goals else 1 if m.home_goals == m.away_goals else 2


def sanity_check(recs: list[MatchRecord], cut: datetime) -> None:
    test = [m for m in recs if m.is_played and m.kickoff_utc >= cut]
    train = [m for m in recs if m.is_played and m.kickoff_utc < cut]
    if not test:
        return
    y = np.array([outcome(m) for m in test])
    base = np.bincount([outcome(m) for m in train], minlength=3) / len(train)
    pm = fit_poisson(recs, cut)
    elo = compute_elo(recs, cut)
    eo = fit_elo_outcomes(recs, elo, cut, skip_first=BURN_IN)
    preds = {
        "base rates": np.tile(base, (len(test), 1)),
        "Elo": np.array([eo.probabilities(rating_diff(elo, m.home_team_id, m.away_team_id,
                                                      neutral=m.neutral)) for m in test]),
        "Poisson": np.array([outcome_probabilities(pm.score_matrix(m.home_team_id,
                             m.away_team_id, neutral=m.neutral)) for m in test]),
    }  # fmt: skip
    print(f"Sanity check: fit before {cut:%Y-%m-%d}, scored on {len(test)} later matches "
          "(lower is better; NOT a validation)")  # fmt: skip
    for name, p in preds.items():
        ll = -np.mean(np.log(p[np.arange(len(y)), y]))
        brier = np.mean(np.sum((p - np.eye(3)[y]) ** 2, axis=1))
        print(f"  {name:10}  log loss {ll:.4f}   Brier {brier:.4f}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--next", type=int, default=5, help="upcoming fixtures per competition")
    ap.add_argument("--cutoff", default="2026-08-01", help="sanity-check cutoff date")
    args = ap.parse_args()

    with connect() as conn:
        recs = load_match_records(conn)
        names = dict(conn.execute("select id, coalesce(short_name, name) from teams").fetchall())

    now = datetime.now(tz=UTC)
    print("=" * 78)
    print(" DEVELOPER PREVIEW: models NOT validated. These are not forecasts.")
    print("=" * 78, "\n")
    sanity_check(recs, datetime.fromisoformat(args.cutoff).replace(tzinfo=UTC))

    elo = compute_elo(recs, now)
    eo = fit_elo_outcomes(recs, elo, now, skip_first=BURN_IN)
    pm = fit_poisson(recs, now)
    print(f"Fitted on {pm.matches_used} matches before {now:%Y-%m-%d %H:%M} UTC "
          f"(Poisson converged: {pm.converged}; home advantage x{np.exp(pm.home_advantage):.2f} "
          f"goals)\n")  # fmt: skip

    for comp in ("EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A", "UCL"):
        season = max(m.season_year for m in recs if m.competition == comp)
        teams = {t for m in recs if m.competition == comp and m.season_year == season
                 for t in (m.home_team_id, m.away_team_id)}  # fmt: skip
        top = sorted(teams, key=elo.rating, reverse=True)[:10]
        print(f"--- {comp} {season}/{(season + 1) % 100:02d} --- Elo top 10:")
        print("    " + ", ".join(f"{names[t]} {elo.rating(t):.0f}" for t in top))

        upcoming = sorted(
            (m for m in recs if m.competition == comp and not m.is_played
             and m.kickoff_utc >= now),
            key=lambda m: m.kickoff_utc,
        )[: args.next]  # fmt: skip
        if upcoming:
            print(
                f"    {'Next fixtures':44} {'Elo  H / D / A':>18}   {'Poisson H / D / A':>18}  xG"
            )
        for m in upcoming:
            e = eo.probabilities(rating_diff(elo, m.home_team_id, m.away_team_id,
                                             neutral=m.neutral))  # fmt: skip
            mat = pm.score_matrix(m.home_team_id, m.away_team_id, neutral=m.neutral)
            p = outcome_probabilities(mat)
            lh, la = pm.expected_goals(m.home_team_id, m.away_team_id, neutral=m.neutral)
            label = f"{m.kickoff_utc:%d %b} {names[m.home_team_id]} v {names[m.away_team_id]}"
            print(f"    {label[:44]:44} "
                  f"{e[0]:5.0%} {e[1]:4.0%} {e[2]:4.0%}   {p[0]:5.0%} {p[1]:4.0%} {p[2]:4.0%}"
                  f"  {lh:.1f}-{la:.1f}")  # fmt: skip
        print()


if __name__ == "__main__":
    main()
