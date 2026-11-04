"""
Refresh everything for the current season in one command:
import latest results -> re-forecast what changed -> publish (quality gates).

This is what the scheduler runs.  Exit code 0 = every step ok or skipped,
1 = at least one step failed (the summary says which and why), 2 = setup error.

Usage (from backend/):
    .venv/Scripts/python scripts/refresh.py                  # the full refresh
    .venv/Scripts/python scripts/refresh.py --no-import      # forecast/publish from stored data
    .venv/Scripts/python scripts/refresh.py --force          # re-forecast even if nothing changed
    .venv/Scripts/python scripts/refresh.py --json report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from app.core.config import settings
from app.core.logging import setup_logging
from app.database.connection import DatabaseConfigError, connect
from app.ingestion.service import ingest_season
from app.providers.football_data_org import FootballDataOrgClient
from app.services.refresh import COMPETITIONS, refresh


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-c", "--competition", action="append", choices=COMPETITIONS)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--sims", type=int, default=10_000)
    ap.add_argument("--no-import", action="store_true", help="skip the provider import")
    ap.add_argument("--no-publish", action="store_true", help="store new runs unpublished")
    ap.add_argument("--force", action="store_true", help="re-forecast even if nothing changed")
    ap.add_argument("--json", type=Path, help="also write the report as JSON to this file")
    args = ap.parse_args()
    setup_logging()

    if not args.no_import and not settings.football_data_org_key:
        print("[setup] FOOTBALL_DATA_ORG_KEY is not set", file=sys.stderr)
        return 2
    try:
        with ExitStack() as stack:
            conn = stack.enter_context(connect())
            ingest = None
            client = None
            if not args.no_import:
                client = stack.enter_context(FootballDataOrgClient(settings.football_data_org_key))
                raw_dir = (
                    None
                    if settings.is_production
                    else Path(__file__).resolve().parents[1] / "raw_responses" / "fdo"
                )

                def ingest(code: str, season: int):  # type: ignore[no-untyped-def]
                    return ingest_season(conn, client, code, season, raw_dir=raw_dir)

            report = refresh(conn, ingest, season=args.season,
                             competitions=args.competition or COMPETITIONS, n_sims=args.sims,
                             force=args.force, publish=not args.no_publish)  # fmt: skip
    except DatabaseConfigError as e:
        print(f"[setup] {e}", file=sys.stderr)
        return 2

    print(f"\nRefresh {report.started_at:%Y-%m-%d %H:%M} UTC, season {report.season}:")
    for s in report.steps:
        mark = {"ok": "OK  ", "skipped": "skip", "failed": "FAIL"}[s.status]
        run = f" run #{s.run_id}" if s.run_id else ""
        print(f"  [{mark}] {s.competition:10} {s.step:8} {s.detail}{run}")
    print(f"  API requests: {report.api_requests}")
    print("RESULT: " + ("FAILED (see FAIL lines)" if report.failed else "OK"))
    if args.json:
        args.json.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
