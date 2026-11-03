"""
Milestone 0 — API-Football Coverage Investigation

Probes the API-Football v3 endpoints for all five V1 competitions:
  EPL (39), La Liga (140), Bundesliga (78), Serie A (135), UCL (2)

Checks:
  1. Account status and quota
  2. League/competition metadata and available seasons
  3. 2026/27 season: teams, fixtures, standings
  4. Historical season depth
  5. Fixture field coverage (scores, status, timestamps)

Outputs a structured report to stdout and saves it to
  docs/milestone-0-coverage-report.md
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the backend app to the path
_SCRIPT_DIR = Path(__file__).resolve().parent          # backend/scripts/
_BACKEND_DIR = _SCRIPT_DIR.parent                      # backend/
_ROOT_DIR = _BACKEND_DIR.parent                        # final-whistle/

sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
import httpx

# ---------------------------------------------------------------------------
# Load environment — try backend/.env then root .env
# ---------------------------------------------------------------------------
_env_loaded = False
for env_path in [_ROOT_DIR / ".env", _BACKEND_DIR / ".env"]:
    if env_path.is_file():
        load_dotenv(env_path, override=True)
        print(f"  Loaded env from: {env_path}")
        _env_loaded = True
        break

if not _env_loaded:
    print("[FATAL] No .env file found.", file=sys.stderr)
    sys.exit(1)

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
if not API_KEY or API_KEY == "replace_me":
    print("[FATAL] API_FOOTBALL_KEY not set. Fill in .env first.", file=sys.stderr)
    sys.exit(1)

BASE_URL = "https://v3.football.api-sports.io"

# ---------------------------------------------------------------------------
# Competitions to investigate
# ---------------------------------------------------------------------------
COMPETITIONS = {
    "EPL": {"id": 39, "name": "English Premier League", "country": "England"},
    "LA_LIGA": {"id": 140, "name": "La Liga", "country": "Spain"},
    "BUNDESLIGA": {"id": 78, "name": "Bundesliga", "country": "Germany"},
    "SERIE_A": {"id": 135, "name": "Serie A", "country": "Italy"},
    "UCL": {"id": 2, "name": "UEFA Champions League", "country": "World"},
}

TARGET_SEASON = 2026  # API-Football uses the start year (2026 = 2026/27)

# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------
client = httpx.Client(
    base_url=BASE_URL,
    headers={"x-apisports-key": API_KEY},
    timeout=30.0,
)

request_count = 0
api_errors: list[str] = []


def api_get(endpoint: str, params: dict | None = None) -> dict:
    """GET request with quota tracking.

    API-Football returns HTTP 200 with an ``errors`` object when the plan
    blocks a request.  Those must be recorded — an empty ``response`` with
    errors is "access denied", NOT "no data exists".
    """
    global request_count
    request_count += 1
    resp = client.get(endpoint, params=params or {})
    resp.raise_for_status()
    data = resp.json()

    remaining = resp.headers.get("x-ratelimit-requests-remaining", "?")
    print(f"  [{request_count}] {endpoint} params={params}  (remaining: {remaining})")

    errors = data.get("errors")
    if errors:
        print(f"  ⚠ API errors: {errors}")
        api_errors.append(f"`{endpoint}` {params}: {errors}")

    return data


# ---------------------------------------------------------------------------
# Investigation functions
# ---------------------------------------------------------------------------
def check_account_status() -> dict:
    """Check account subscription and daily quota."""
    print("\n" + "=" * 60)
    print("1. ACCOUNT STATUS")
    print("=" * 60)
    data = api_get("/status")
    account = data.get("response", {}).get("account", {})
    subscription = data.get("response", {}).get("subscription", {})
    requests_info = data.get("response", {}).get("requests", {})

    info = {
        "name": (account.get("firstname") or "") + " " + (account.get("lastname") or ""),
        "email": account.get("email") or "",
        "plan": subscription.get("plan") or "unknown",
        "end_date": subscription.get("end") or "",
        "daily_limit": requests_info.get("limit_day") or "?",
        "requests_today": requests_info.get("current") or "?",
    }

    print(f"  Plan: {info['plan']}")
    print(f"  Daily limit: {info['daily_limit']}")
    print(f"  Used today: {info['requests_today']}")
    return info


def check_league_metadata(code: str, comp: dict) -> dict:
    """Fetch league info and available seasons."""
    league_id = comp["id"]
    data = api_get("/leagues", {"id": league_id})
    results = data.get("response", [])

    if not results:
        return {"error": f"No data returned for league ID {league_id}"}

    league_info = results[0].get("league", {})
    country_info = results[0].get("country", {})
    seasons_list = results[0].get("seasons", [])

    available_seasons = [s["year"] for s in seasons_list]
    has_target = TARGET_SEASON in available_seasons

    info = {
        "api_name": league_info.get("name", ""),
        "api_id": league_info.get("id"),
        "type": league_info.get("type", ""),
        "country": country_info.get("name", ""),
        "total_seasons": len(available_seasons),
        "oldest_season": min(available_seasons) if available_seasons else None,
        "newest_season": max(available_seasons) if available_seasons else None,
        "has_2026_season": has_target,
        "all_seasons": sorted(available_seasons),
    }

    print(f"  API name: {info['api_name']}")
    print(f"  Type: {info['type']}")
    print(f"  Seasons available: {info['total_seasons']} ({info['oldest_season']}–{info['newest_season']})")
    print(f"  2026/27 season available: {'✅ YES' if has_target else '❌ NO'}")

    return info


def check_season_teams(league_id: int, season: int) -> dict:
    """Check teams for a specific season."""
    data = api_get("/teams", {"league": league_id, "season": season})
    results = data.get("response", [])
    teams = [
        {"id": r["team"]["id"], "name": r["team"]["name"]}
        for r in results
        if r.get("team")
    ]

    info = {
        "team_count": len(teams),
        "teams": teams,
    }
    print(f"  Teams: {info['team_count']}")
    if teams:
        names = [t["name"] for t in teams[:5]]
        print(f"  Sample: {', '.join(names)}{'...' if len(teams) > 5 else ''}")
    return info


def check_season_fixtures(league_id: int, season: int) -> dict:
    """Check fixtures for a specific season — coverage, statuses, fields."""
    data = api_get("/fixtures", {"league": league_id, "season": season})
    results = data.get("response", [])

    statuses: dict[str, int] = {}
    has_scores = 0
    has_kickoff = 0
    missing_scores_finished = 0
    sample_fixture = None

    for fx in results:
        fixture_info = fx.get("fixture", {})
        status_short = fixture_info.get("status", {}).get("short", "?")
        statuses[status_short] = statuses.get(status_short, 0) + 1

        if fixture_info.get("date"):
            has_kickoff += 1

        goals = fx.get("goals", {})
        if goals.get("home") is not None and goals.get("away") is not None:
            has_scores += 1
        elif status_short == "FT":
            missing_scores_finished += 1

        if sample_fixture is None and status_short == "FT":
            sample_fixture = fx

    info = {
        "total_fixtures": len(results),
        "statuses": statuses,
        "with_scores": has_scores,
        "with_kickoff": has_kickoff,
        "missing_scores_on_finished": missing_scores_finished,
    }

    print(f"  Total fixtures: {info['total_fixtures']}")
    print(f"  Statuses: {json.dumps(statuses, indent=2)}")
    print(f"  With scores: {has_scores}")
    print(f"  With kickoff time: {has_kickoff}")
    if missing_scores_finished > 0:
        print(f"  ⚠ Finished but missing scores: {missing_scores_finished}")

    # Check field coverage on sample fixture
    if sample_fixture:
        fx_fields = list(sample_fixture.get("fixture", {}).keys())
        team_fields = list(sample_fixture.get("teams", {}).get("home", {}).keys()) if sample_fixture.get("teams") else []
        score_fields = list(sample_fixture.get("score", {}).keys()) if sample_fixture.get("score") else []
        info["sample_fixture_fields"] = fx_fields
        info["sample_team_fields"] = team_fields
        info["sample_score_fields"] = score_fields
        print(f"  Fixture fields: {fx_fields}")
        print(f"  Team fields: {team_fields}")
        print(f"  Score sections: {score_fields}")

    return info


def check_standings(league_id: int, season: int) -> dict:
    """Check if standings are available."""
    data = api_get("/standings", {"league": league_id, "season": season})
    results = data.get("response", [])

    if not results:
        return {"available": False, "groups": 0, "teams": 0}

    league_data = results[0].get("league", {})
    standings_groups = league_data.get("standings", [])

    total_teams = sum(len(g) for g in standings_groups)

    info = {
        "available": True,
        "groups": len(standings_groups),
        "teams": total_teams,
    }

    print(f"  Standings available: ✅ YES")
    print(f"  Groups/tables: {info['groups']}")
    print(f"  Teams in standings: {info['teams']}")

    # Show top 3 from first group
    if standings_groups and standings_groups[0]:
        top3 = standings_groups[0][:3]
        for entry in top3:
            team = entry.get("team", {})
            print(f"    {entry.get('rank', '?')}. {team.get('name', '?')} — "
                  f"Pts: {entry.get('points', '?')}, "
                  f"P: {entry.get('all', {}).get('played', '?')}")

    return info


# ---------------------------------------------------------------------------
# Main investigation
# ---------------------------------------------------------------------------
def main() -> None:
    report_lines: list[str] = []

    def log(line: str = "") -> None:
        print(line)
        report_lines.append(line)

    log("# Milestone 0 — API-Football Coverage Report")
    log(f"\nGenerated: {datetime.now(tz=__import__('datetime').timezone.utc).isoformat()}")
    log(f"Target season: {TARGET_SEASON} (2026/27)")
    log("")

    # 1. Account status
    account = check_account_status()
    log("\n## Account Status\n")
    log(f"- **Plan:** {account.get('plan', '?')}")
    log(f"- **Daily request limit:** {account.get('daily_limit', '?')}")
    log(f"- **Requests used today (before this script):** {account.get('requests_today', '?')}")
    log("")

    # 2. Per-competition investigation
    all_results: dict[str, dict] = {}

    for code, comp in COMPETITIONS.items():
        log(f"\n## {comp['name']} ({code}) — League ID {comp['id']}\n")
        print(f"\n{'=' * 60}")
        print(f"INVESTIGATING: {comp['name']} ({code})")
        print(f"{'=' * 60}")

        result: dict = {"code": code, "comp": comp}

        # League metadata & seasons
        print("\n--- League metadata ---")
        result["metadata"] = check_league_metadata(code, comp)
        log(f"- **API name:** {result['metadata'].get('api_name', '?')}")
        log(f"- **Type:** {result['metadata'].get('type', '?')}")
        log(f"- **Seasons available:** {result['metadata'].get('total_seasons', '?')} "
            f"({result['metadata'].get('oldest_season', '?')}–{result['metadata'].get('newest_season', '?')})")
        log(f"- **2026/27 season present:** {'✅ Yes' if result['metadata'].get('has_2026_season') else '❌ No'}")

        # Teams for 2026
        if result["metadata"].get("has_2026_season"):
            print(f"\n--- Teams (season {TARGET_SEASON}) ---")
            result["teams"] = check_season_teams(comp["id"], TARGET_SEASON)
            log(f"- **Teams (2026/27):** {result['teams'].get('team_count', '?')}")

            print(f"\n--- Fixtures (season {TARGET_SEASON}) ---")
            result["fixtures"] = check_season_fixtures(comp["id"], TARGET_SEASON)
            log(f"- **Fixtures (2026/27):** {result['fixtures'].get('total_fixtures', '?')}")
            log(f"- **With scores:** {result['fixtures'].get('with_scores', '?')}")
            log(f"- **Statuses:** {json.dumps(result['fixtures'].get('statuses', {}))}")

            print(f"\n--- Standings (season {TARGET_SEASON}) ---")
            result["standings"] = check_standings(comp["id"], TARGET_SEASON)
            log(f"- **Standings available:** {'✅ Yes' if result['standings'].get('available') else '❌ No'}")
            if result["standings"].get("available"):
                log(f"- **Teams in standings:** {result['standings'].get('teams', '?')}")
        else:
            log(f"- ⚠ **2026/27 season not found — skipping teams/fixtures/standings checks**")

        # Historical depth: check a few older seasons
        available_seasons = result["metadata"].get("all_seasons", [])
        historical = [s for s in available_seasons if s < TARGET_SEASON]
        result["historical_seasons"] = historical
        log(f"- **Historical seasons (before 2026):** {len(historical)}")
        if historical:
            log(f"- **Oldest historical:** {min(historical)}")
            log(f"- **Recent historical:** {sorted(historical)[-5:]}")

        log("")
        all_results[code] = result

    # 3. Summary
    log("\n## Summary\n")
    log("| Competition | 2026/27 | Teams | Fixtures | Standings | Historical Seasons |")
    log("|---|---|---|---|---|---|")
    for code, r in all_results.items():
        has_season = "✅" if r.get("metadata", {}).get("has_2026_season") else "❌"
        teams = r.get("teams", {}).get("team_count", "—")
        fixtures = r.get("fixtures", {}).get("total_fixtures", "—")
        standings = "✅" if r.get("standings", {}).get("available") else "—"
        hist = len(r.get("historical_seasons", []))
        log(f"| {code} | {has_season} | {teams} | {fixtures} | {standings} | {hist} |")

    log(f"\n**Total API requests used by this script:** {request_count}")
    log("")

    log("\n## API Errors\n")
    if api_errors:
        log("⚠ Zero counts above may reflect plan restrictions, not missing data:\n")
        for err in api_errors:
            log(f"- {err}")
    else:
        log("None.")
    log("")

    # 4. Quota warning
    log("\n## Quota Impact\n")
    log(f"This investigation used **{request_count}** of the daily 100-request budget.")
    remaining_str = f"{100 - request_count}" if isinstance(account.get("daily_limit"), int) else "unknown"
    log(f"Estimated remaining today: ~{remaining_str}")
    log("")

    # Save report
    report_path = _ROOT_DIR / "docs" / "milestone-0-coverage-report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n✅ Report saved to: {report_path}")


if __name__ == "__main__":
    main()
    client.close()
