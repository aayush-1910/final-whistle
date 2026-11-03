"""
Ingest one competition-season from football-data.org into the database.

Flow:  fetch (3 requests) -> save raw JSON -> normalize -> upsert in ONE
transaction -> cross-check standings -> record the run.

Every run is recorded in ``ingestion_runs``, including failures, so a problem
is never silent.  Status meanings:
  succeeded — all records valid and the rebuilt table matches the provider's
  partial   — data stored, but some records were invalid or the tables disagree
  failed    — nothing from this run was stored (see ``error``)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from app.database import repository as repo
from app.ingestion.consistency import compare_with_standings
from app.ingestion.normalize_fdo import (
    Issue,
    normalize_matches,
    normalize_season,
    normalize_standings,
    normalize_team,
)
from app.providers.football_data_org import (
    PROVIDER_NAME,
    FootballDataOrgClient,
    FootballDataOrgError,
)

logger = logging.getLogger(__name__)

DEFAULT_RAW_DIR = Path(__file__).resolve().parents[2] / "raw_responses" / "fdo"


@dataclass
class IngestionResult:
    run_id: int
    competition: str
    season_year: int
    status: str = "running"
    requests: int = 0
    fixtures_total: int = 0
    inserted: int = 0
    updated: int = 0
    issues: list[Issue] = field(default_factory=list)
    consistency: dict[str, Any] | None = None
    error: str | None = None


def _save_raw(raw_dir: Path | None, name: str, data: dict[str, Any]) -> None:
    if raw_dir is None:
        return
    day = raw_dir / datetime.now(tz=UTC).strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    (day / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def _collect_teams(teams_raw: dict[str, Any], matches_raw: dict[str, Any]) -> list[Any]:
    """Teams from the team list, plus any that only appear in matches."""
    seen: dict[str, Any] = {}
    for t in teams_raw.get("teams", []):
        seen[str(t["id"])] = normalize_team(t)
    for m in matches_raw.get("matches", []):
        for side in ("homeTeam", "awayTeam"):
            t = m.get(side) or {}
            if t.get("id") is not None and str(t["id"]) not in seen:
                seen[str(t["id"])] = normalize_team(t)
    return list(seen.values())


def ingest_season(
    conn: psycopg.Connection[Any],
    client: FootballDataOrgClient,
    competition_code: str,
    season_year: int,
    *,
    raw_dir: Path | None = DEFAULT_RAW_DIR,
) -> IngestionResult:
    """Ingest one competition-season.  ``conn`` must be in autocommit mode."""
    if not conn.autocommit:
        raise ValueError("ingest_season needs an autocommit connection (it manages transactions)")

    competition_id, ext_code = repo.get_competition(conn, competition_code, PROVIDER_NAME)
    run_id = repo.start_run(conn, PROVIDER_NAME, competition_id)
    result = IngestionResult(run_id, competition_code, season_year)
    requests_before = client.request_count
    tag = f"{ext_code}_{season_year}"

    try:
        teams_raw = client.get_teams(ext_code, season_year)
        _save_raw(raw_dir, f"{tag}_teams", teams_raw)
        matches_raw = client.get_matches(ext_code, season_year)
        _save_raw(raw_dir, f"{tag}_matches", matches_raw)
        standings_raw: dict[str, Any] | None = None
        try:
            standings_raw = client.get_standings(ext_code, season_year)
            _save_raw(raw_dir, f"{tag}_standings", standings_raw)
        except FootballDataOrgError as e:
            result.issues.append(Issue("skipped", "standings", str(e)))

        season = normalize_season(competition_code, teams_raw["season"])
        if season.start_year != season_year:
            raise ValueError(f"Asked for season {season_year}, provider returned {season.label}")

        with conn.transaction():
            season_id = repo.upsert_season(conn, competition_id, season)
            team_ids = repo.upsert_teams(conn, _collect_teams(teams_raw, matches_raw),
                                         PROVIDER_NAME)  # fmt: skip
            repo.link_season_teams(
                conn, season_id, [team_ids[str(t["id"])] for t in teams_raw.get("teams", [])]
            )
            normalized = normalize_matches(matches_raw.get("matches", []), team_ids, season_id)
            result.issues.extend(normalized.issues)
            result.fixtures_total = len(normalized.fixtures)
            result.inserted, result.updated = repo.upsert_fixtures(
                conn, normalized.fixtures, run_id
            )
            if standings_raw is not None:
                rows = normalize_standings(standings_raw, team_ids)
                repo.insert_standings(conn, season_id, run_id, rows)
                check = compare_with_standings(normalized.fixtures, rows)
                result.consistency = {
                    "teams_checked": check.teams_checked,
                    "ok": check.ok,
                    "discrepancies": [asdict(d) for d in check.discrepancies],
                }

        clean = not any(i.kind == "invalid" for i in result.issues) and (
            result.consistency is None or result.consistency["ok"]
        )
        result.status = "succeeded" if clean else "partial"
        result.requests = client.request_count - requests_before
        repo.finish_run(
            conn, run_id, status=result.status, season_id=season_id,
            request_count=result.requests, inserted=result.inserted, updated=result.updated,
            issues=result.issues, consistency=result.consistency,
        )  # fmt: skip
    except Exception as e:
        result.status = "failed"
        result.error = f"{type(e).__name__}: {e}"[:2000]
        result.requests = client.request_count - requests_before
        logger.exception("Ingestion failed for %s %s", competition_code, season_year)
        repo.finish_run(
            conn, run_id, status="failed", request_count=result.requests,
            issues=result.issues, error=result.error,
        )  # fmt: skip
    return result
