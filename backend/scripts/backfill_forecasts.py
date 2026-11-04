"""
Recompute this season's forecast as it would have looked after each past matchday
(plus pre-season), so the dashboard can show how the title race evolved.

Each run uses ONLY results before its cutoff: the model is refitted at that cutoff
and later results are treated as unplayed (no leakage). Runs are stored as
historical backfill runs (``is_backfill``) with the current production model, so
they are clearly distinguishable from forecasts made at the time.

Idempotent: matchdays that already have a run of the current model version, or that
are not earlier than the latest stored run, are skipped.

Usage (from backend/):
    .venv/Scripts/python scripts/backfill_forecasts.py                 # all 5, list only
    .venv/Scripts/python scripts/backfill_forecasts.py --save          # compute + store
    .venv/Scripts/python scripts/backfill_forecasts.py -c EPL --save --publish
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from app.database import publishing
from app.database.connection import connect
from app.database.forecasts import git_commit
from app.models import config
from app.models.data import load_match_records
from app.models.poisson import fit_poisson
from app.services.forecasting import save_run, simulate_competition
from app.simulations.rules import load_rules

LEAGUES = ["EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A", "UCL"]
MATCH_LENGTH = timedelta(hours=2, minutes=30)  # kickoff -> safely after full time
WINDOW = timedelta(days=4)  # a matchday's fixtures normally sit within this of its median


def matchday_cutoffs(conn: Any, code: str, year: int) -> list[tuple[int, datetime]]:
    """[(0, pre-season cutoff), (md, cutoff after that matchday), ...] for completed
    matchdays. Fixtures far from their matchday's median kickoff (postponed and
    rescheduled) do not delay the cutoff; they simply count once played."""
    stage = "league_stage" if code == "UCL" else "regular_season"
    rows = conn.execute(
        """select f.matchday, f.kickoff_utc, f.status from fixtures f
             join seasons s on s.id = f.season_id join competitions c on c.id = s.competition_id
            where c.code = %s and s.start_year = %s and f.stage = %s
              and f.matchday is not null and f.kickoff_utc is not null""",
        (code, year, stage),
    ).fetchall()
    if not rows:
        return []
    by_md: dict[int, list[tuple[datetime, str]]] = {}
    for md, ko, status in rows:
        by_md.setdefault(md, []).append((ko, status))
    out = [(0, min(ko for _, ko, _ in rows) - timedelta(minutes=1))]
    now = datetime.now(tz=UTC)
    for md in sorted(by_md):
        ks = by_md[md]
        median = statistics.median_low(ko.timestamp() for ko, _ in ks)
        core = [(ko, st) for ko, st in ks if abs(ko.timestamp() - median) <= WINDOW.total_seconds()]
        if not all(st in ("finished", "awarded") for _, st in core):
            break  # first matchday not yet complete
        cutoff = max(ko for ko, _ in core) + MATCH_LENGTH
        if cutoff > now:
            break
        out.append((md, cutoff))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-c", "--competition", action="append", choices=LEAGUES)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--sims", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=20261103)
    ap.add_argument("--save", action="store_true", help="store as historical backfill runs")
    ap.add_argument("--publish", action="store_true",
                    help="publish stored runs that pass the gates (needs --save)")  # fmt: skip
    ap.add_argument("--accept-secondary-rules", action="store_true")
    args = ap.parse_args()
    if args.publish and not args.save:
        ap.error("--publish needs --save")

    with connect() as conn:
        recs = load_match_records(conn)
        code_version = git_commit()
        for comp in args.competition or LEAGUES:
            rules = load_rules(comp, args.season)
            latest = conn.execute(
                """select max(r.data_cutoff) from model_runs r join seasons s on s.id = r.season_id
                     join competitions c on c.id = r.competition_id
                    where c.code = %s and s.start_year = %s and not r.is_backfill""",
                (comp, args.season),
            ).fetchone()[0]
            done = {
                row[0]
                for row in conn.execute(
                    """select r.data_cutoff from model_runs r join seasons s on s.id = r.season_id
                         join competitions c on c.id = r.competition_id
                        where c.code = %s and s.start_year = %s and r.model_version = %s""",
                    (comp, args.season, config.MODEL_VERSION),
                )
            }
            cutoffs = matchday_cutoffs(conn, comp, args.season)
            print(f"--- {comp} {args.season}: {len(cutoffs) - 1} completed matchdays ---")
            for md, cutoff in cutoffs:
                label = "pre-season" if md == 0 else f"after matchday {md}"
                if cutoff in done:
                    print(f"  {label:22} {cutoff:%Y-%m-%d %H:%M}  already stored")
                    continue
                if latest is not None and cutoff >= latest:
                    print(f"  {label:22} {cutoff:%Y-%m-%d %H:%M}  covered by the current run")
                    continue
                if not args.save:
                    print(f"  {label:22} {cutoff:%Y-%m-%d %H:%M}  to compute")
                    continue
                t0 = time.time()
                model = fit_poisson(recs, cutoff, config.POISSON)
                # UCL: league phase only - knockout draws are not reconstructible as of a
                # past date.
                f, _ = simulate_competition(conn, recs, model, comp, args.season, cutoff,
                                            n_sims=args.sims, seed=args.seed,
                                            knockout=False)  # fmt: skip
                f.notes = [*f.notes, f"Historical run: computed {datetime.now(tz=UTC):%Y-%m-%d} "
                           f"using only data before {cutoff:%Y-%m-%d %H:%M} UTC."]  # fmt: skip
                run_id = save_run(conn, f, model, rules, code_version=code_version,
                                  is_backfill=True, backfill={"matchday": md})  # fmt: skip
                msg = f"saved run #{run_id} ({time.time() - t0:.0f}s)"
                if args.publish:
                    _, checks = publishing.publish_checks(
                        conn, run_id, accept_secondary_rules=args.accept_secondary_rules
                    )
                    failed = [c.name for c in checks if not c.ok]
                    if failed:
                        msg += f", NOT published ({', '.join(failed)})"
                    else:
                        publishing.publish(conn, run_id)
                        msg += ", published"
                print(f"  {label:22} {cutoff:%Y-%m-%d %H:%M}  {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
