"""
Database reads/writes for source data.

Functions take an open connection; the caller owns transactions.  Writes are
idempotent upserts keyed on provider IDs, so re-running an ingestion never
duplicates rows, and unchanged rows are not rewritten.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from typing import Any

import psycopg

from app.domain.models import (
    Fixture,
    FixtureStatus,
    MatchDuration,
    ProviderRef,
    Season,
    Stage,
    StandingRow,
    Team,
)

Conn = psycopg.Connection[Any]


class NotFoundError(LookupError):
    pass


# ---------------------------------------------------------------------------
# Competitions / seasons
# ---------------------------------------------------------------------------
def get_competition(conn: Conn, code: str, provider: str) -> tuple[int, str]:
    """Return (competition_id, provider external id) for an internal code."""
    row = conn.execute(
        """select c.id, p.external_id
             from competitions c
             join competition_provider_ids p on p.competition_id = c.id and p.provider = %s
            where c.code = %s""",
        (provider, code),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Competition {code!r} has no {provider} mapping")
    return int(row[0]), str(row[1])


def season_id(conn: Conn, competition_code: str, start_year: int) -> int:
    row = conn.execute(
        """select s.id from seasons s join competitions c on c.id = s.competition_id
            where c.code = %s and s.start_year = %s""",
        (competition_code, start_year),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"No season {competition_code} {start_year}")
    return int(row[0])


def upsert_season(conn: Conn, competition_id: int, season: Season) -> int:
    row = conn.execute(
        """insert into seasons (competition_id, start_year, start_date, end_date)
           values (%s, %s, %s, %s)
           on conflict (competition_id, start_year) do update
              set start_date = coalesce(excluded.start_date, seasons.start_date),
                  end_date   = coalesce(excluded.end_date, seasons.end_date)
           returning id""",
        (competition_id, season.start_year, season.start_date, season.end_date),
    ).fetchone()
    assert row is not None
    return int(row[0])


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------
def upsert_teams(conn: Conn, teams: Sequence[Team], provider: str) -> dict[str, int]:
    """Create or refresh teams; return {provider external id: canonical team id}."""
    by_ext: dict[str, Team] = {}
    for t in teams:
        ext = t.external_id(provider)
        if ext is None:
            raise ValueError(f"Team {t.name!r} has no {provider} id")
        by_ext[ext] = t

    existing = dict(
        conn.execute(
            """select external_id, team_id from team_provider_ids
                where provider = %s and external_id = any(%s)""",
            (provider, list(by_ext)),
        ).fetchall()
    )

    with conn.cursor() as cur:
        # Refresh names of known teams only when something changed.
        if existing:
            cur.executemany(
                """update teams set name = %s, short_name = %s, tla = %s,
                          country = coalesce(%s, country), updated_at = now()
                    where id = %s
                      and (name, short_name, tla, coalesce(%s, country))
                          is distinct from (name, short_name, tla, country)""",
                [
                    (t.name, t.short_name, t.tla, t.country, existing[e], t.country)
                    for e, t in by_ext.items()
                    if e in existing
                ],
            )
        missing = [(e, t) for e, t in by_ext.items() if e not in existing]
        if missing:
            cur.executemany(
                """with t as (
                       insert into teams (name, short_name, tla, country)
                       values (%s, %s, %s, %s) returning id)
                   insert into team_provider_ids (team_id, provider, external_id)
                   select id, %s, %s from t
                   returning external_id, team_id""",
                [(t.name, t.short_name, t.tla, t.country, provider, e) for e, t in missing],
                returning=True,
            )
            while True:
                for ext, team_id in cur.fetchall():
                    existing[ext] = team_id
                if not cur.nextset():
                    break
    return {k: int(v) for k, v in existing.items()}


def link_season_teams(conn: Conn, season_id: int, team_ids: Iterable[int]) -> None:
    conn.execute(
        """insert into season_teams (season_id, team_id)
           select %s, unnest(%s::int[]) on conflict do nothing""",
        (season_id, list(team_ids)),
    )


# ---------------------------------------------------------------------------
# Ingestion runs
# ---------------------------------------------------------------------------
def start_run(conn: Conn, provider: str, competition_id: int | None) -> int:
    row = conn.execute(
        "insert into ingestion_runs (provider, competition_id) values (%s, %s) returning id",
        (provider, competition_id),
    ).fetchone()
    assert row is not None
    return int(row[0])


def finish_run(
    conn: Conn,
    run_id: int,
    *,
    status: str,
    season_id: int | None = None,
    request_count: int = 0,
    inserted: int = 0,
    updated: int = 0,
    issues: Sequence[Any] = (),
    consistency: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """update ingestion_runs
              set finished_at = now(), status = %s, season_id = coalesce(%s, season_id),
                  request_count = %s, fixtures_inserted = %s, fixtures_updated = %s,
                  issues = %s::jsonb, consistency = %s::jsonb, error = %s
            where id = %s""",
        (
            status,
            season_id,
            request_count,
            inserted,
            updated,
            json.dumps([asdict(i) for i in issues]),
            json.dumps(consistency) if consistency is not None else None,
            error,
            run_id,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_FIXTURE_COLS = (
    "season_id",
    "home_team_id",
    "away_team_id",
    "kickoff_utc",
    "status",
    "stage",
    "group_name",
    "matchday",
    "home_score",
    "away_score",
    "duration",
    "home_score_90",
    "away_score_90",
    "home_penalties",
    "away_penalties",
    "provider",
    "provider_fixture_id",
    "provider_status",
)
# Columns whose change counts as an update (everything except the key).
_COMPARED = _FIXTURE_COLS[:15] + ("provider_status",)


def _fixture_row(f: Fixture) -> tuple[Any, ...]:
    if f.provider_ref is None:
        raise ValueError("Fixture must carry a provider_ref to be stored")
    return (
        f.season_id,
        f.home_team_id,
        f.away_team_id,
        f.kickoff_utc,
        f.status.value,
        f.stage.value,
        f.group,
        f.matchday,
        f.home_score,
        f.away_score,
        f.duration.value,
        f.home_score_90,
        f.away_score_90,
        f.home_penalties,
        f.away_penalties,
        f.provider_ref.provider,
        f.provider_ref.external_id,
        f.provider_status,
    )


def upsert_fixtures(conn: Conn, fixtures: Sequence[Fixture], run_id: int) -> tuple[int, int]:
    """Insert new fixtures and update changed ones.  Returns (inserted, updated)."""
    if not fixtures:
        return 0, 0
    cols = ", ".join(_FIXTURE_COLS)
    conn.execute(
        f"""create temp table tmp_fixtures on commit drop as
            select {cols} from fixtures with no data"""
    )
    with conn.cursor().copy(f"copy tmp_fixtures ({cols}) from stdin") as copy:
        for f in fixtures:
            copy.write_row(_fixture_row(f))

    set_clause = ", ".join(f"{c} = excluded.{c}" for c in _COMPARED)
    old = ", ".join(f"fixtures.{c}" for c in _COMPARED)
    new = ", ".join(f"excluded.{c}" for c in _COMPARED)
    rows = conn.execute(
        f"""insert into fixtures ({cols}, first_seen_run_id, last_updated_run_id)
            select {cols}, %(run)s, %(run)s from tmp_fixtures
            on conflict (provider, provider_fixture_id) do update
               set {set_clause}, last_updated_run_id = %(run)s, updated_at = now()
             where ({old}) is distinct from ({new})
            returning (xmax = 0) as inserted""",
        {"run": run_id},
    ).fetchall()
    conn.execute("drop table if exists tmp_fixtures")
    inserted = sum(1 for (i,) in rows if i)
    return inserted, len(rows) - inserted


def load_fixtures(conn: Conn, season_id: int) -> list[Fixture]:
    """Read a season's fixtures back as validated domain objects."""
    cols = ", ".join(("id", *_FIXTURE_COLS))
    out: list[Fixture] = []
    for r in conn.execute(
        f"select {cols} from fixtures where season_id = %s order by kickoff_utc, id", (season_id,)
    ):
        (fid, season, home, away, kickoff, status, stage, group, md, hs, as_, dur,
         h90, a90, hp, ap, provider, ext, pstatus) = r  # fmt: skip
        out.append(
            Fixture(
                id=fid,
                season_id=season,
                home_team_id=home,
                away_team_id=away,
                kickoff_utc=kickoff,
                status=FixtureStatus(status),
                stage=Stage(stage),
                group=group,
                matchday=md,
                home_score=hs,
                away_score=as_,
                duration=MatchDuration(dur),
                home_score_90=h90,
                away_score_90=a90,
                home_penalties=hp,
                away_penalties=ap,
                provider_status=pstatus,
                provider_ref=ProviderRef(provider, ext),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------
def insert_standings(conn: Conn, season_id: int, run_id: int, rows: Sequence[StandingRow]) -> int:
    snap = conn.execute(
        """insert into standings_snapshots (season_id, ingestion_run_id)
           values (%s, %s) returning id""",
        (season_id, run_id),
    ).fetchone()
    assert snap is not None
    with conn.cursor() as cur:
        cur.executemany(
            """insert into standings_rows (snapshot_id, team_id, position, played, won, drawn,
                                           lost, goals_for, goals_against, points)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                (
                    snap[0],
                    r.team_id,
                    r.position,
                    r.played,
                    r.won,
                    r.drawn,
                    r.lost,
                    r.goals_for,
                    r.goals_against,
                    r.points,
                )
                for r in rows
            ],  # fmt: skip
        )
    return int(snap[0])
