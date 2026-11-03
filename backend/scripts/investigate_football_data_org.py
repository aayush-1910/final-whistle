"""
Milestone 0 — football-data.org coverage investigation.

For each V1 competition, checks with REAL requests:
  1. Competition metadata and the seasons it lists
  2. 2026/27 teams, matches (status breakdown, score coverage), standings
  3. Which historical seasons this token can actually fetch

Every error is recorded — a rejected request is reported as "denied",
never as "0 rows".  Raw responses are saved to backend/raw_responses/fdo/
(git-ignored).  Report: docs/milestone-0-football-data-org-report.md

Usage (from backend/):  python scripts/investigate_football_data_org.py
Takes ~4 minutes because of the free-tier limit of 10 requests/minute.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.providers.football_data_org import (  # noqa: E402
    COMPETITION_CODES,
    FootballDataOrgClient,
    FootballDataOrgError,
)

TARGET_SEASON = 2026
HISTORY_PROBES = [2025, 2023, 2020, 2015]  # spot-checks, not exhaustive
RAW_DIR = _BACKEND_DIR / "raw_responses" / "fdo"
REPORT = _ROOT_DIR / "docs" / "milestone-0-football-data-org-report.md"


def main() -> None:
    token = settings.football_data_org_key
    if not token:
        sys.exit(
            "[FATAL] FOOTBALL_DATA_ORG_KEY is not set in .env "
            "(get a free token at https://www.football-data.org/client/register)."
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    lines: list[str] = []

    def log(s: str = "") -> None:
        print(s)
        lines.append(s)

    def call(name: str, fn, *args, **kw) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
        try:
            data = fn(*args, **kw)
        except FootballDataOrgError as e:
            errors.append(f"`{name}`: HTTP {e.status_code} — {e.message}")
            print(f"  ✗ {name}: HTTP {e.status_code} {e.message}")
            return None
        (RAW_DIR / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        print(f"  ✓ {name}")
        return data

    log("# Milestone 0 — football-data.org Coverage Report\n")
    log(f"Generated: {datetime.now(tz=UTC).isoformat()}  ")
    log(f"Target season: {TARGET_SEASON} ({TARGET_SEASON}/{(TARGET_SEASON + 1) % 100:02d})\n")

    summary: list[str] = []
    with FootballDataOrgClient(token) as client:
        for key, code in COMPETITION_CODES.items():
            log(f"\n## {key} (`{code}`)\n")

            meta = call(f"{code}_meta", client.get_competition, code)
            if meta:
                seasons = meta.get("seasons", [])
                starts = sorted(int(s["startDate"][:4]) for s in seasons if s.get("startDate"))
                cur = meta.get("currentSeason") or {}
                log(f"- **Name:** {meta.get('name')} | type: {meta.get('type')}")
                log(
                    f"- **Current season:** {cur.get('startDate')} → {cur.get('endDate')}, "
                    f"matchday {cur.get('currentMatchday')}"
                )
                log(
                    f"- **Seasons listed in metadata:** {len(starts)} "
                    f"({starts[0] if starts else '?'}–{starts[-1] if starts else '?'}) "
                    f"_(listed ≠ accessible)_"
                )

            teams = call(f"{code}_{TARGET_SEASON}_teams", client.get_teams, code, TARGET_SEASON)
            n_teams = len(teams.get("teams", [])) if teams else None
            log(f"- **{TARGET_SEASON} teams:** {n_teams if teams else 'DENIED'}")

            matches = call(
                f"{code}_{TARGET_SEASON}_matches", client.get_matches, code, TARGET_SEASON
            )
            if matches:
                ms = matches.get("matches", [])
                statuses = Counter(m.get("status") for m in ms)
                fin = [m for m in ms if m.get("status") == "FINISHED"]
                fin_scored = sum(
                    1
                    for m in fin
                    if (m.get("score") or {}).get("fullTime", {}).get("home") is not None
                    and (m.get("score") or {}).get("fullTime", {}).get("away") is not None
                )
                stages = Counter(m.get("stage") for m in ms)
                log(f"- **{TARGET_SEASON} matches:** {len(ms)} | statuses: {dict(statuses)}")
                log(f"- **Finished with full-time score:** {fin_scored}/{len(fin)}")
                log(f"- **Stages:** {dict(stages)}")
                n_matches: Any = len(ms)
            else:
                log(f"- **{TARGET_SEASON} matches:** DENIED")
                n_matches = "DENIED"

            st = call(
                f"{code}_{TARGET_SEASON}_standings", client.get_standings, code, TARGET_SEASON
            )
            if st:
                tables = st.get("standings", [])
                log(
                    f"- **{TARGET_SEASON} standings:** {len(tables)} table(s), types "
                    f"{sorted({t.get('type') for t in tables})}"
                )
            else:
                log(f"- **{TARGET_SEASON} standings:** DENIED")

            ok_hist: list[int] = []
            for yr in HISTORY_PROBES:
                h = call(f"{code}_{yr}_matches", client.get_matches, code, yr, status="FINISHED")
                if h is not None:
                    ok_hist.append(yr)
                    log(f"- **{yr} finished matches:** {len(h.get('matches', []))}")
                else:
                    log(f"- **{yr} matches:** DENIED")

            summary.append(
                f"| {key} | {n_teams if teams else 'DENIED'} | {n_matches} | "
                f"{'✅' if st else 'DENIED'} | {ok_hist or 'none'} |"
            )

        log("\n## Summary\n")
        log(
            f"| Competition | {TARGET_SEASON} teams | {TARGET_SEASON} matches | Standings "
            f"| Accessible history (probed {HISTORY_PROBES}) |"
        )
        log("|---|---|---|---|---|")
        for row in summary:
            log(row)

        log("\n## Errors\n")
        log("\n".join(f"- {e}" for e in errors) if errors else "None.")
        log(f"\n**Requests made:** {client.request_count}")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport saved: {REPORT}")


if __name__ == "__main__":
    main()
