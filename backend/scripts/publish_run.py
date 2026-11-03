"""
Publish a forecast run (make it visible through the API without ?preview=true).

Checks before publishing (README §1, §15 quality gates):
  1. the run exists, completed, and is not already published
  2. its model version is the current production version (models/config.py)
  3. stored backtests exist (match-level and season-level), so performance
     claims point to evidence
  4. the competition's rules come from a PRIMARY source, or you explicitly
     accept secondary-sourced rules with --accept-secondary-rules
  5. the run used the latest imported data (its cutoff is after the last import)

Dry run by default; add --yes to publish.  --unpublish reverses a publication.

Usage (from backend/):
    .venv/Scripts/python scripts/publish_run.py --latest -c EPL            # check only
    .venv/Scripts/python scripts/publish_run.py --latest -c EPL --yes      # publish
    .venv/Scripts/python scripts/publish_run.py --run 12 --unpublish --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from app.database.connection import connect
from app.models import config
from app.simulations.rules import RulesNotFoundError, load_rules


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--run", type=int, help="model run id")
    target.add_argument("--latest", action="store_true", help="latest run of -c / --season")
    ap.add_argument("-c", "--competition")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--accept-secondary-rules", action="store_true")
    ap.add_argument("--unpublish", action="store_true")
    ap.add_argument("--yes", action="store_true", help="actually write the change")
    args = ap.parse_args()

    with connect() as conn:
        if args.latest:
            if not args.competition:
                ap.error("--latest needs -c/--competition")
            row = conn.execute(
                """select r.id from model_runs r join seasons s on s.id = r.season_id
                     join competitions c on c.id = r.competition_id
                    where c.code = %s and s.start_year = %s order by r.run_at desc, r.id desc limit 1""",
                (args.competition, args.season),
            ).fetchone()
            if row is None:
                print("No run found.")
                return 1
            run_id = int(row[0])
        else:
            run_id = args.run
        run = conn.execute(
            """select r.id, r.status, r.is_published, r.model_version, r.data_cutoff, c.code,
                      s.start_year, c.id,
                      (select max(finished_at) from ingestion_runs i
                        where i.competition_id = c.id and i.status in ('succeeded', 'partial'))
                 from model_runs r join competitions c on c.id = r.competition_id
                 join seasons s on s.id = r.season_id where r.id = %s""",
            (run_id,),
        ).fetchone()
        if run is None:
            print(f"Run {run_id} not found.")
            return 1
        _, status, published, version, cutoff, code, year, _, last_import = run

        if args.unpublish:
            print(
                f"Run #{run_id} ({code} {year}) is {'published' if published else 'not published'}."
            )
            if published and args.yes:
                conn.execute("update model_runs set is_published = false where id = %s", (run_id,))
                print("Unpublished.")
            elif published:
                print("Dry run: add --yes to unpublish.")
            return 0

        backtests = dict(
            conn.execute(
                "select kind, max(model_version) from backtest_runs group by kind"
            ).fetchall()
        )
        try:
            quality = load_rules(code, year).source_quality
        except RulesNotFoundError:
            quality = None

        checks = [
            ("run completed", status == "completed", status),
            ("not already published", not published, "already published" if published else "ok"),
            ("current model version", version == config.MODEL_VERSION,
             f"run {version}, production {config.MODEL_VERSION}"),
            ("match-level backtest stored", "match" in backtests, f"latest for {backtests.get('match')}"),
            ("season-level backtest stored", "season" in backtests, f"latest for {backtests.get('season')}"),
            ("rules from a primary source", quality == "primary" or (quality == "secondary" and args.accept_secondary_rules),
             f"{quality}" + (" (accepted via --accept-secondary-rules)" if quality == "secondary" and args.accept_secondary_rules else "")),
            ("used the latest imported data", last_import is None or cutoff >= last_import,
             f"cutoff {cutoff:%Y-%m-%d %H:%M}, last import {last_import:%Y-%m-%d %H:%M}" if last_import else "no import"),
        ]  # fmt: skip
        print(
            f"Run #{run_id}: {code} {year}, model {version}, data cutoff {cutoff:%Y-%m-%d %H:%M} UTC\n"
        )
        for name, ok, detail in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:32} {detail}")
        if not all(ok for _, ok, _ in checks):
            print("\nNot published: fix the failing checks first.")
            return 1
        if not args.yes:
            print("\nAll checks pass. Dry run: add --yes to publish.")
            return 0
        conn.execute("update model_runs set is_published = true where id = %s", (run_id,))
        print("\nPublished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
