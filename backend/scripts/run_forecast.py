"""
Simulate the rest of the season for domestic leagues and (optionally) store it.

Usage (from backend/):
    .venv/Scripts/python scripts/run_forecast.py                    # all 4 leagues, print only
    .venv/Scripts/python scripts/run_forecast.py -c EPL --save      # store as an UNPUBLISHED run
    .venv/Scripts/python scripts/run_forecast.py --sims 20000 --seed 7

THE MODEL IS NOT VALIDATED YET (Milestone 6).  Stored runs are unpublished.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from app.database.connection import connect
from app.database.forecasts import git_commit, save_season_forecast
from app.models.data import load_match_records
from app.models.poisson import fit_poisson
from app.simulations.domestic import simulate_league
from app.simulations.rules import load_rules

LEAGUES = ["EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A"]
MODEL_NAME, MODEL_VERSION = "poisson-montecarlo", "0.1.0"
SHORT = {
    "champions_league": "UCL",
    "europa_league": "UEL",
    "conference_league": "UECL",
    "relegation_playoff": "Rel PO",
    "relegation": "Relegated",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-c", "--competition", action="append", choices=LEAGUES)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--sims", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=20261103)
    ap.add_argument("--save", action="store_true", help="store as an unpublished model run")
    args = ap.parse_args()

    as_of = datetime.now(tz=UTC)
    with connect() as conn:
        recs = load_match_records(conn)
        names = dict(conn.execute("select id, coalesce(short_name, name) from teams").fetchall())
        model = fit_poisson(recs, as_of)
        code = git_commit()
        print("=" * 78)
        print(" DEVELOPER OUTPUT: model NOT validated. These are not published forecasts.")
        print("=" * 78)
        print(f"Data cutoff {as_of:%Y-%m-%d %H:%M} UTC | {args.sims} sims | seed {args.seed} | "
              f"code {code}\n")  # fmt: skip

        for comp in args.competition or LEAGUES:
            rules = load_rules(comp, args.season)
            t0 = time.time()
            f = simulate_league(recs, comp, args.season, model, rules, as_of,
                                n_sims=args.sims, seed=args.seed)  # fmt: skip
            exp_pos = f.expected_position
            zones = [z.key for z in rules.zones if z.key != "champion"]
            print(f"--- {comp} {args.season}/{(args.season + 1) % 100:02d} "
                  f"({f.completed_matches} played, {len(f.matches)} to simulate, "
                  f"{time.time() - t0:.1f}s) ---")  # fmt: skip
            header = f"{'':3}{'Team':18}{'Pts':>4}{'xPts':>6}{'xPos':>6}{'Title':>7}"
            print(header + "".join(f"{SHORT.get(z, z[:10]):>11}" for z in zones))
            for i, t in enumerate(sorted(f.team_ids, key=lambda x: exp_pos[x]), start=1):
                row = (f"{i:<3}{names[t][:17]:18}{f.current_points[t]:>4}"
                       f"{f.expected_points[t]:>6.1f}{exp_pos[t]:>6.1f}{f.title_probs[t]:>7.1%}")  # fmt: skip
                print(row + "".join(f"{f.zone_probs[z][t]:>11.1%}" for z in zones))
            for note in f.notes:
                print(f"  note: {note}")
            print(f"  rules: {rules.source_quality} source, verified {rules.verified_on}")
            if args.save:
                params = {
                    "poisson": model.params.to_dict(),
                    "poisson_fit": {"mu": model.mu, "home_advantage": model.home_advantage,
                                    "matches_used": model.matches_used},
                    "rules": {"tiebreakers": [t.value for t in rules.tiebreakers],
                              "playoff_positions": list(rules.playoff_positions),
                              "source": rules.source, "source_quality": rules.source_quality},
                }  # fmt: skip
                run_id = save_season_forecast(
                    conn, f, model_name=MODEL_NAME, model_version=MODEL_VERSION,
                    params=params, code_version=code,
                )  # fmt: skip
                print(f"  saved as model run #{run_id} (unpublished)")
            print()


if __name__ == "__main__":
    main()
