"""
Apply pending database migrations (backend/migrations/*.sql).

Usage (from backend/):
    .venv/Scripts/python scripts/migrate.py            # apply
    .venv/Scripts/python scripts/migrate.py --status   # list pending only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import connect
from app.database.migrate import migrate, pending


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="show pending migrations only")
    args = parser.parse_args()

    with connect() as conn:
        if args.status:
            with conn.transaction():
                todo = pending(conn)
            print("Pending:", [f.name for f in todo] or "none")
            return
        applied = migrate(conn)
    print("Applied:", applied or "nothing (already up to date)")


if __name__ == "__main__":
    main()
