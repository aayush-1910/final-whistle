"""
Simulate the rest of the season for domestic leagues and (optionally) store it.

Usage (from backend/):
    .venv/Scripts/python scripts/run_forecast.py                    # all 4 leagues, print only
    .venv/Scripts/python scripts/run_forecast.py -c EPL --save      # store as an UNPUBLISHED run
    .venv/Scripts/python scripts/run_forecast.py --sims 20000 --seed 7

Stored runs are unpublished: publish with publish_run.py, or use refresh.py for the
whole import -> forecast -> publish pipeline.
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
from app.database.forecasts import git_commit
from app.models import config
from app.models.data import load_match_records
from app.models.poisson import fit_poisson
from app.services.forecasting import save_run, simulate_competition
from app.simulations.ucl import UCLForecast

LEAGUES = ["EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A", "UCL"]
MODEL_NAME, MODEL_VERSION = config.MODEL_NAME, config.MODEL_VERSION
SHORT = {
    "champions_league": "UCL",
    "europa_league": "UEL",
    "conference_league": "UECL",
    "relegation_playoff": "Rel PO",
    "relegation": "Relegated",
    "round_of_16": "Top 8",
    "knockout_playoffs": "9-24",
    "eliminated": "25-36",
}
ROUND_SHORT = {
    "round_of_16": "R16",
    "quarter_finals": "QF",
    "semi_finals": "SF",
    "final": "Final",
    "winner": "Win",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-c", "--competition", action="append", choices=LEAGUES)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--sims", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=20261103)
    ap.add_argument("--save", action="store_true", help="store as an unpublished model run")
    args = ap.parse_args()

    with connect() as conn:
        # Database clock: import timestamps come from it (see app/services/refresh.py).
        as_of = max(datetime.now(tz=UTC), conn.execute("select now()").fetchone()[0])
        recs = load_match_records(conn)
        names = dict(conn.execute("select id, coalesce(short_name, name) from teams").fetchall())
        model = fit_poisson(recs, as_of, config.POISSON)
        code = git_commit()
        print("=" * 78)
        print(" DEVELOPER OUTPUT: model NOT validated. These are not published forecasts.")
        print("=" * 78)
        print(f"Data cutoff {as_of:%Y-%m-%d %H:%M} UTC | {args.sims} sims | seed {args.seed} | "
              f"code {code}\n")  # fmt: skip

        for comp in args.competition or LEAGUES:
            t0 = time.time()
            f, rules = simulate_competition(conn, recs, model, comp, args.season, as_of,
                                            n_sims=args.sims, seed=args.seed)  # fmt: skip
            exp_pos = f.expected_position
            zones = [z.key for z in rules.zones if z.key != "champion"]
            print(f"--- {comp} {args.season}/{(args.season + 1) % 100:02d} "
                  f"({f.completed_matches} played, {len(f.matches)} to simulate, "
                  f"{time.time() - t0:.1f}s) ---")  # fmt: skip
            is_ucl = isinstance(f, UCLForecast)
            rounds = list(ROUND_SHORT) if is_ucl else []
            first = (
                "" if is_ucl else f"{'Title':>7}"
            )  # UCL: P(1st in league phase) is not the title
            header = f"{'':3}{'Team':18}{'Pts':>4}{'xPts':>6}{'xPos':>6}{first}"
            print(
                header
                + "".join(f"{SHORT.get(z, z[:10]):>11}" for z in zones)
                + "".join(f"{ROUND_SHORT[r]:>7}" for r in rounds)
            )
            order = sorted(f.team_ids, key=lambda x: exp_pos[x])
            if isinstance(f, UCLForecast):
                order = sorted(f.team_ids, key=lambda x: -f.round_probs["winner"][x])
            for i, t in enumerate(order, start=1):
                title = "" if is_ucl else f"{f.title_probs[t]:>7.1%}"
                row = (f"{i:<3}{names[t][:17]:18}{f.current_points[t]:>4}"
                       f"{f.expected_points[t]:>6.1f}{exp_pos[t]:>6.1f}{title}")  # fmt: skip
                row += "".join(f"{f.zone_probs[z][t]:>11.1%}" for z in zones)
                if isinstance(f, UCLForecast):
                    row += "".join(f"{f.round_probs[r][t]:>7.1%}" for r in rounds)
                print(row)
            for note in f.notes:
                print(f"  note: {note}")
            print(f"  rules: {rules.source_quality} source, verified {rules.verified_on}")
            if args.save:
                run_id = save_run(conn, f, model, rules, code_version=code)
                print(f"  saved as model run #{run_id} (unpublished)")
            print()


if __name__ == "__main__":
    main()
