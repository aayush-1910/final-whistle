"""
Import competitions/seasons from football-data.org into the database.

Usage (from backend/):
    .venv/Scripts/python scripts/ingest.py                         # all 5, season 2026
    .venv/Scripts/python scripts/ingest.py -c EPL -c UCL -s 2026
    .venv/Scripts/python scripts/ingest.py --all-seasons           # 2023-2026 (free-tier range)

Each competition-season costs 3 API requests; the client keeps under the
free tier's 10 requests/minute automatically.  Exit code is 1 if any run
failed, so this can be used from a scheduler later.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from app.core.config import settings
from app.database.connection import connect
from app.ingestion.service import ingest_season
from app.providers.football_data_org import COMPETITION_CODES, FootballDataOrgClient

FREE_TIER_SEASONS = [2023, 2024, 2025, 2026]  # verified 2026-11-03


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--competition", action="append", choices=list(COMPETITION_CODES))
    parser.add_argument("-s", "--season", action="append", type=int)
    parser.add_argument("--all-seasons", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")

    if not settings.football_data_org_key:
        print("[FATAL] FOOTBALL_DATA_ORG_KEY is not set in .env", file=sys.stderr)
        return 2

    comps = args.competition or list(COMPETITION_CODES)
    seasons = FREE_TIER_SEASONS if args.all_seasons else (args.season or [2026])
    print(f"Ingesting {comps} x {seasons}  (~{3 * len(comps) * len(seasons)} requests)\n")

    failed = False
    with connect() as conn, FootballDataOrgClient(settings.football_data_org_key) as client:
        for season in seasons:
            for comp in comps:
                r = ingest_season(conn, client, comp, season)
                cons = r.consistency
                table = "n/a" if cons is None else ("OK" if cons["ok"] else
                        f"{len(cons['discrepancies'])} mismatches")  # fmt: skip
                invalid = sum(1 for i in r.issues if i.kind == "invalid")
                skipped = sum(1 for i in r.issues if i.kind == "skipped")
                print(
                    f"[{r.status:9}] {comp:10} {season}  fixtures {r.fixtures_total:4} "
                    f"(+{r.inserted} new, {r.updated} updated)  table check: {table}  "
                    f"invalid: {invalid}  skipped: {skipped}  run #{r.run_id}"
                )
                for i in r.issues:
                    print(f"    - {i.kind}: {i.provider_id}: {i.message}")
                if cons and not cons["ok"]:
                    for d in cons["discrepancies"][:5]:
                        print(f"    - mismatch: {d}")
                if r.error:
                    print(f"    ! {r.error}")
                failed |= r.status == "failed"
    print(f"\nAPI requests used: {client.request_count}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
