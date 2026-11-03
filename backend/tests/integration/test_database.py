"""
Database integration tests.

Run with:  RUN_DB_TESTS=1 python -m pytest tests/integration
They build the full schema inside a throwaway Postgres schema (fw_test_<random>)
in the configured database, then DROP it — real tables are never touched.
The football-data.org API is faked with httpx.MockTransport (no quota used).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import psycopg
import pytest

from app.database import repository as repo
from app.database.connection import connect
from app.database.migrate import migrate
from app.ingestion.service import ingest_season
from app.providers.football_data_org import FootballDataOrgClient, RateLimiter

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to run database tests"
)


@pytest.fixture
def db() -> Iterator[psycopg.Connection[Any]]:
    schema = f"fw_test_{uuid.uuid4().hex[:10]}"
    conn = connect()
    try:
        conn.execute(f"create schema {schema}")
        conn.execute(f"set search_path to {schema}")
        migrate(conn)
        yield conn
    finally:
        conn.execute(f"drop schema if exists {schema} cascade")
        conn.close()


# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------
TEAMS = [
    {"id": 57, "name": "Arsenal FC", "shortName": "Arsenal", "tla": "ARS", "area": {"name": "England"}},
    {"id": 61, "name": "Chelsea FC", "shortName": "Chelsea", "tla": "CHE", "area": {"name": "England"}},
    {"id": 65, "name": "Manchester City FC", "shortName": "Man City", "tla": "MCI", "area": {"name": "England"}},
]  # fmt: skip
SEASON = {"id": 1, "startDate": "2026-08-21", "endDate": "2027-05-30"}


def _match(mid: int, home: int, away: int, score: tuple[int, int] | None) -> dict[str, Any]:
    return {
        "id": mid,
        "utcDate": "2026-08-21T19:00:00Z",
        "status": "FINISHED" if score else "TIMED",
        "matchday": 1,
        "stage": "REGULAR_SEASON",
        "group": None,
        "homeTeam": {"id": home},
        "awayTeam": {"id": away},
        "score": {
            "duration": "REGULAR",
            "fullTime": {"home": score[0], "away": score[1]} if score else {"home": None, "away": None},
        },
    }  # fmt: skip


def _row(
    pos: int, tid: int, p: int, w: int, d: int, lo: int, gf: int, ga: int, pts: int
) -> dict[str, Any]:
    return {"position": pos, "team": {"id": tid}, "playedGames": p, "won": w, "draw": d,
            "lost": lo, "goalsFor": gf, "goalsAgainst": ga, "points": pts}  # fmt: skip


class FakeAPI:
    def __init__(self) -> None:
        self.matches = [_match(1, 57, 61, (2, 1)), _match(2, 65, 57, None)]
        self.standings = [
            _row(1, 57, 1, 1, 0, 0, 2, 1, 3),
            _row(2, 65, 0, 0, 0, 0, 0, 0, 0),
            _row(3, 61, 1, 0, 0, 1, 1, 2, 0),
        ]
        self.fail_matches = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/teams"):
            return httpx.Response(200, json={"season": SEASON, "teams": TEAMS})
        if path.endswith("/matches"):
            if self.fail_matches:
                return httpx.Response(500, json={"message": "boom"})
            return httpx.Response(200, json={"matches": self.matches})
        if path.endswith("/standings"):
            return httpx.Response(
                200, json={"standings": [{"type": "TOTAL", "table": self.standings}]}
            )
        return httpx.Response(404, json={"message": "unknown"})

    def client(self) -> FootballDataOrgClient:
        return FootballDataOrgClient(
            "t", transport=httpx.MockTransport(self.handler), rate_limiter=RateLimiter(1000, 60)
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_migrations_seed_and_are_idempotent(db: psycopg.Connection[Any]) -> None:
    assert migrate(db) == []
    codes = [r[0] for r in db.execute("select code from competitions order by id")]
    assert codes == ["EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A", "UCL"]
    assert repo.get_competition(db, "EPL", "football_data_org")[1] == "PL"


def test_rls_enabled_on_every_table(db: psycopg.Connection[Any]) -> None:
    rows = db.execute(
        """select c.relname, c.relrowsecurity from pg_class c
             join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = current_schema() and c.relkind = 'r'"""
    ).fetchall()
    assert rows and all(rls for _, rls in rows), rows


def test_ingest_then_reingest_is_idempotent(db: psycopg.Connection[Any]) -> None:
    api = FakeAPI()
    with api.client() as c:
        first = ingest_season(db, c, "EPL", 2026, raw_dir=None)
        assert first.status == "succeeded", first
        assert (first.inserted, first.updated, first.requests) == (2, 0, 3)
        assert first.consistency and first.consistency["ok"]

        second = ingest_season(db, c, "EPL", 2026, raw_dir=None)
        assert (second.inserted, second.updated) == (0, 0)

        # Match 2 gets played: exactly one update.
        api.matches[1] = _match(2, 65, 57, (0, 0))
        api.standings = [
            _row(1, 57, 2, 1, 1, 0, 2, 1, 4),
            _row(2, 65, 1, 0, 1, 0, 0, 0, 1),
            _row(3, 61, 1, 0, 0, 1, 1, 2, 0),
        ]
        third = ingest_season(db, c, "EPL", 2026, raw_dir=None)
        assert (third.inserted, third.updated, third.status) == (0, 1, "succeeded")

    assert db.execute("select count(*) from fixtures").fetchone() == (2,)
    assert db.execute("select count(*) from teams").fetchone() == (3,)
    assert db.execute("select count(*) from season_teams").fetchone() == (3,)
    assert db.execute("select count(*) from standings_snapshots").fetchone() == (3,)
    statuses = [r[0] for r in db.execute("select status from ingestion_runs order by id")]
    assert statuses == ["succeeded"] * 3


def test_fixtures_round_trip(db: psycopg.Connection[Any]) -> None:
    with FakeAPI().client() as c:
        ingest_season(db, c, "EPL", 2026, raw_dir=None)
    season_id = db.execute("select id from seasons").fetchone()[0]  # type: ignore[index]
    loaded = repo.load_fixtures(db, season_id)
    assert [(f.home_score, f.away_score, f.status.value) for f in loaded] == [
        (2, 1, "finished"),
        (None, None, "scheduled"),
    ]


def test_standings_mismatch_marks_run_partial(db: psycopg.Connection[Any]) -> None:
    api = FakeAPI()
    api.standings[0] = _row(1, 57, 1, 1, 0, 0, 2, 1, 0)  # e.g. a points deduction
    with api.client() as c:
        r = ingest_season(db, c, "EPL", 2026, raw_dir=None)
    assert r.status == "partial"
    assert r.consistency and r.consistency["discrepancies"][0]["field"] == "points"


def test_provider_failure_is_recorded_and_stores_nothing(db: psycopg.Connection[Any]) -> None:
    api = FakeAPI()
    api.fail_matches = True
    with api.client() as c:
        r = ingest_season(db, c, "EPL", 2026, raw_dir=None)
    assert r.status == "failed" and r.error and "500" in r.error
    assert db.execute("select count(*) from fixtures").fetchone() == (0,)
    run = db.execute("select status, error from ingestion_runs").fetchone()
    assert run is not None and run[0] == "failed" and "boom" in run[1]


def test_database_rejects_team_playing_itself(db: psycopg.Connection[Any]) -> None:
    with FakeAPI().client() as c:
        ingest_season(db, c, "EPL", 2026, raw_dir=None)
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "update fixtures set away_team_id = home_team_id where provider_fixture_id = '1'"
        )


def test_season_forecast_round_trip(db: psycopg.Connection[Any]) -> None:
    from datetime import UTC, datetime, timedelta
    from itertools import permutations

    from app.database.forecasts import save_season_forecast
    from app.domain.models import LeagueRules, Tiebreaker, Zone
    from app.models.data import MatchRecord
    from app.models.poisson import PoissonModel, PoissonParams
    from app.simulations.domestic import simulate_league

    with FakeAPI().client() as c:
        ingest_season(db, c, "EPL", 2026, raw_dir=None)
    team_ids = [r[0] for r in db.execute("select id from teams order by id")]
    t0 = datetime(2026, 8, 1, tzinfo=UTC)
    recs = [
        MatchRecord(i, t0 + timedelta(days=i + 10), "EPL", 2026, h, a, None, None)
        for i, (h, a) in enumerate(permutations(team_ids, 2))
    ]
    rules = LeagueRules("EPL", 2026, 3, 3, 1, (Tiebreaker.POINTS, Tiebreaker.PLAYOFF),
                        zones=(Zone("champion", "C", 1, 1),))  # fmt: skip
    model = PoissonModel(PoissonParams(), t0, 0.3, 0.2, {t: 0.0 for t in team_ids},
                         {t: 0.0 for t in team_ids}, 100, True)  # fmt: skip
    f = simulate_league(recs, "EPL", 2026, model, rules, t0, n_sims=500, seed=1)
    # Synthetic fixture ids don't exist in the DB; store them as provider-missing fixtures.
    from dataclasses import replace

    f.matches = [replace(m, fixture_id=None) for m in f.matches]
    run_id = save_season_forecast(
        db, f, model_name="test", model_version="0", params={"x": 1}, code_version="abc"
    )
    run = db.execute("select is_published, simulation_count, seed from model_runs").fetchone()
    assert run == (False, 500, 1)
    rows = db.execute(
        "select team_id, position_probs, zone_probs from season_forecasts where model_run_id = %s",
        (run_id,),
    ).fetchall()
    assert len(rows) == 3 and all(abs(sum(p) - 1) < 1e-9 for _, p, _ in rows)
    assert sum(z["champion"] for _, _, z in rows) == pytest.approx(1)
    assert db.execute("select count(*) from match_forecasts").fetchone() == (6,)
