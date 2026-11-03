"""
Publish a forecast run (make it visible through the API without ?preview=true).

Checks before publishing (README §1, §15 quality gates; app/database/publishing.py):
  1. the run exists, completed, and is not already published
  2. its model version is the current production version (models/config.py)
  3. stored backtests exist (match-level and season-level), so performance
     claims point to evidence
  4. the competition's rules come from a PRIMARY source, or you explicitly
     accept secondary-sourced rules with --accept-secondary-rules
  5. the run used the latest imported data (its cutoff is after the last import);
     historical backfill runs instead must have a cutoff before the last import

Dry run by default; add --yes to publish.  --unpublish reverses a publication.

Usage (from backend/):
    .venv/Scripts/python scripts/publish_run.py --latest -c EPL            # check only
    .venv/Scripts/python scripts/publish_run.py --latest -c EPL --yes      # publish
    .venv/Scripts/python scripts/publish_run.py --backfill -c EPL --yes    # all unpublished history
    .venv/Scripts/python scripts/publish_run.py --run 12 --unpublish --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from app.database import publishing
from app.database.connection import connect


def _check_and_publish(conn, run_id: int, args: argparse.Namespace) -> bool:  # type: ignore[no-untyped-def]
    state, checks = publishing.publish_checks(
        conn, run_id, accept_secondary_rules=args.accept_secondary_rules
    )
    kind = " (historical backfill)" if state.is_backfill else ""
    print(f"Run #{run_id}: {state.competition} {state.season}, model {state.model_version}, "
          f"data cutoff {state.data_cutoff:%Y-%m-%d %H:%M} UTC{kind}")  # fmt: skip
    for c in checks:
        print(f"  [{'PASS' if c.ok else 'FAIL'}] {c.name:34} {c.detail}")
    if not all(c.ok for c in checks):
        print("  Not published: fix the failing checks first.\n")
        return False
    if not args.yes:
        print("  All checks pass. Dry run: add --yes to publish.\n")
        return True
    publishing.publish(conn, run_id)
    print("  Published.\n")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--run", type=int, help="model run id")
    target.add_argument("--latest", action="store_true", help="latest run of -c / --season")
    target.add_argument("--backfill", action="store_true",
                        help="every unpublished historical backfill run of -c / --season")  # fmt: skip
    ap.add_argument("-c", "--competition")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--accept-secondary-rules", action="store_true")
    ap.add_argument("--unpublish", action="store_true")
    ap.add_argument("--yes", action="store_true", help="actually write the change")
    args = ap.parse_args()

    with connect() as conn:
        if args.latest or args.backfill:
            if not args.competition:
                ap.error("--latest/--backfill need -c/--competition")
            base = """select r.id from model_runs r join seasons s on s.id = r.season_id
                        join competitions c on c.id = r.competition_id
                       where c.code = %s and s.start_year = %s"""
            if args.latest:
                rows = conn.execute(
                    base + " order by r.data_cutoff desc, r.run_at desc, r.id desc limit 1",
                    (args.competition, args.season),
                ).fetchall()
            else:
                rows = conn.execute(
                    base + " and r.is_backfill and not r.is_published order by r.data_cutoff",
                    (args.competition, args.season),
                ).fetchall()
            run_ids = [int(r[0]) for r in rows]
            if not run_ids:
                print("No run found.")
                return 1
        else:
            run_ids = [args.run]

        if args.unpublish:
            for run_id in run_ids:
                state = publishing.run_state(conn, run_id)
                if state is None:
                    print(f"Run {run_id} not found.")
                    return 1
                print(f"Run #{run_id} ({state.competition} {state.season}) is "
                      f"{'published' if state.is_published else 'not published'}.")  # fmt: skip
                if state.is_published and args.yes:
                    publishing.unpublish(conn, run_id)
                    print("Unpublished.")
                elif state.is_published:
                    print("Dry run: add --yes to unpublish.")
            return 0

        ok = True
        for run_id in run_ids:
            try:
                ok = _check_and_publish(conn, run_id, args) and ok
            except LookupError as e:
                print(e)
                return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
