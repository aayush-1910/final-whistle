"""
API integration tests: the real FastAPI app against a throwaway Postgres schema.

Run with:  RUN_DB_TESTS=1 python -m pytest tests/integration
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import permutations
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import create_pool
from app.database.connection import connect
from app.database.forecasts import save_backtest, save_season_forecast
from app.database.migrate import migrate
from app.domain.models import LeagueRules, Tiebreaker, Zone
from app.ingestion.service import ingest_season
from app.main import create_app
from app.models.data import MatchRecord
from app.models.poisson import PoissonModel, PoissonParams
from app.simulations.domestic import simulate_league
from tests.integration.test_database import FakeAPI, _match

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to run database tests"
)


@pytest.fixture(scope="module")
def env() -> Iterator[dict[str, Any]]:
    """Schema with: EPL 2026 (3 teams, 1 result, 1 upcoming fixture), one saved forecast run
    (unpublished), and one backtest row."""
    schema = f"fw_test_{uuid.uuid4().hex[:10]}"
    admin = connect()
    admin.execute(f"create schema {schema}")
    admin.execute(f"set search_path to {schema}")
    try:
        migrate(admin)
        api = FakeAPI()
        soon = datetime.now(tz=UTC) + timedelta(days=2)
        api.matches[1] = _match(2, 65, 57, None) | {
            "utcDate": soon.isoformat().replace("+00:00", "Z")
        }
        with api.client() as c:
            ingest_season(admin, c, "EPL", 2026, raw_dir=None)
        ids = {
            int(e): t
            for e, t in admin.execute("select external_id, team_id from team_provider_ids")
        }
        fixture_ids = dict(admin.execute("select provider_fixture_id, id from fixtures").fetchall())

        # A forecast run whose matches reference the real upcoming fixture.
        t0 = datetime.now(tz=UTC)
        teams = sorted(ids.values())
        recs = [
            MatchRecord(int(fixture_ids["2"]) if (h, a) == (ids[65], ids[57]) else 10_000 + i,
                        t0 + timedelta(days=i + 1), "EPL", 2026, h, a, None, None)
            for i, (h, a) in enumerate(permutations(teams, 2))
        ]  # fmt: skip
        rules = LeagueRules("EPL", 2026, 3, 3, 1, (Tiebreaker.POINTS, Tiebreaker.PLAYOFF),
                            zones=(Zone("champion", "Champions", 1, 1),))  # fmt: skip
        model = PoissonModel(
            PoissonParams(), t0, 0.3, 0.2, {ids[57]: 0.4}, {ids[57]: 0.2}, 100, True
        )
        f = simulate_league(recs, "EPL", 2026, model, rules, t0, n_sims=500, seed=1)
        from dataclasses import replace

        f.matches = [m if m.fixture_id == int(fixture_ids["2"]) else replace(m, fixture_id=None)
                     for m in f.matches]  # fmt: skip
        run_id = save_season_forecast(admin, f, model_name="test", model_version="9.9.9",
                                      params={}, code_version="abc")  # fmt: skip
        save_backtest(admin, kind="match", model_name="test", model_version="9.9.9",
                      params={"x": 1}, tuning_window={"start": "a"}, test_window={"start": "b"},
                      metrics={"overall": {"Poisson": {"log_loss": 0.98}}}, code_version="abc")  # fmt: skip

        pool = create_pool(search_path=schema, max_size=2)
        with TestClient(create_app(pool)) as client:
            yield {"client": client, "ids": ids, "run_id": run_id, "fixture": int(fixture_ids["2"]),
                   "admin": admin}  # fmt: skip
        pool.close()
    finally:
        admin.execute(f"drop schema if exists {schema} cascade")
        admin.close()


def test_health(env: dict[str, Any]) -> None:
    c = env["client"]
    assert c.get("/api/v1/health").json()["status"] == "ok"
    assert c.get("/api/v1/health/ready").json()["database"] == "ok"


def test_competitions(env: dict[str, Any]) -> None:
    comps = {x["code"]: x for x in env["client"].get("/api/v1/competitions").json()}
    assert set(comps) == {"EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A", "UCL"}
    epl = comps["EPL"]
    assert epl["current_season"] == 2026 and epl["season_label"] == "2026/27"
    assert (
        epl["freshness"]["last_ingested_at"] is not None and epl["freshness"]["is_stale"] is False
    )
    assert epl["latest_published_run"] is None and epl["preview_run_available"] is True
    assert comps["UCL"]["current_season"] is None and comps["UCL"]["freshness"]["is_stale"] is True


def test_standings(env: dict[str, Any]) -> None:
    b = env["client"].get("/api/v1/competitions/EPL/seasons/2026/standings").json()
    rows = b["rows"]
    assert [r["team"]["short_name"] for r in rows] == ["Arsenal", "Man City", "Chelsea"]
    assert rows[0] | {"team": None} == rows[0] | {
        "team": None, "position": 1, "played": 1, "won": 1, "drawn": 0, "lost": 0,
        "goals_for": 2, "goals_against": 1, "goal_difference": 1, "points": 3, "form": ["W"],
    }  # fmt: skip
    assert rows[1]["played"] == 0 and "head-to-head" in b["ordering_note"]


def test_forecast_is_hidden_until_published(env: dict[str, Any]) -> None:
    c, admin = env["client"], env["admin"]
    url = "/api/v1/competitions/EPL/seasons/2026/forecast"
    r = c.get(url)
    assert r.status_code == 404 and "preview=true" in r.json()["detail"]
    p = c.get(url + "?preview=true").json()
    assert p["run"]["is_published"] is False and p["run"]["model_version"] == "9.9.9"
    assert p["run"]["rules_source_quality"] == "primary"  # rules/2026/EPL.json
    assert abs(sum(t["zone_probs"]["champion"] for t in p["teams"]) - 1) < 1e-9
    assert all(abs(sum(t["position_probs"]) - 1) < 1e-9 for t in p["teams"])
    admin.execute("update model_runs set is_published = true where id = %s", (env["run_id"],))
    try:
        pub = c.get(url).json()
        assert pub["run"]["is_published"] is True and pub["run"]["run_id"] == env["run_id"]
    finally:
        admin.execute("update model_runs set is_published = false where id = %s", (env["run_id"],))


def test_upcoming_and_fixture_detail(env: dict[str, Any]) -> None:
    c = env["client"]
    plain = c.get("/api/v1/fixtures/upcoming?days=7").json()
    assert len(plain) == 1 and plain[0]["forecast"] is None  # unpublished run not shown
    prev = c.get("/api/v1/fixtures/upcoming?days=7&preview=true&competition=EPL").json()
    fc = prev[0]["forecast"]
    assert (
        fc["is_published"] is False and abs(fc["p_home"] + fc["p_draw"] + fc["p_away"] - 1) < 1e-6
    )
    d = c.get(f"/api/v1/fixtures/{env['fixture']}?preview=true").json()
    probs = [x["probability"] for x in d["likely_scorelines"]]
    assert len(probs) == 10 and probs == sorted(probs, reverse=True)
    assert len(d["score_matrix"]) == 6 and d["disclaimer"]
    assert c.get(f"/api/v1/fixtures/{env['fixture']}").json()["forecast"] is None


def test_team_endpoints(env: dict[str, Any]) -> None:
    c, arsenal = env["client"], env["ids"][57]
    t = c.get(f"/api/v1/teams/{arsenal}").json()
    assert t["team"]["name"] == "Arsenal FC" and t["country"] == "England"
    assert t["seasons"] == [
        {"competition": "EPL", "season": 2026, "position": 1, "played": 1, "points": 3}
    ]
    assert len(t["recent_results"]) == 1 and len(t["upcoming_fixtures"]) == 1
    h = c.get(
        f"/api/v1/teams/{arsenal}/forecast-history?competition=EPL&season=2026&preview=true"
    ).json()
    assert [p["run_id"] for p in h["points"]] == [env["run_id"]]
    assert (
        c.get(f"/api/v1/teams/{arsenal}/forecast-history?competition=EPL&season=2026").json()[
            "points"
        ]
        == []
    )


def test_models_and_runs(env: dict[str, Any]) -> None:
    c = env["client"]
    v = c.get("/api/v1/models/versions").json()
    assert v[0]["model_version"] == "9.9.9" and v[0]["published_runs"] == 0
    perf = c.get("/api/v1/models/performance").json()
    assert perf["match_level"]["metrics"]["overall"]["Poisson"]["log_loss"] == 0.98
    assert perf["season_level"] is None
    run = c.get(f"/api/v1/forecasts/{env['run_id']}").json()
    assert run["competition"] == "EPL" and len(run["teams"]) == 3


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/api/v1/competitions/XYZ/seasons/2026/standings", 404),
        ("/api/v1/competitions/EPL/seasons/2019/standings", 404),
        ("/api/v1/competitions/epl/seasons/2026/standings", 422),
        ("/api/v1/fixtures/999999999", 404),
        ("/api/v1/fixtures/0", 422),
        ("/api/v1/teams/999999", 404),
        ("/api/v1/forecasts/999999", 404),
        ("/api/v1/fixtures/upcoming?days=999", 422),
    ],
)
def test_errors(env: dict[str, Any], path: str, status: int) -> None:
    assert env["client"].get(path).status_code == status


def test_api_is_read_only(env: dict[str, Any]) -> None:
    c = env["client"]
    for method in ("post", "put", "patch", "delete"):
        r = getattr(c, method)("/api/v1/competitions")
        assert r.status_code == 405
    assert all(
        m == {"GET"} or m == {"HEAD", "GET"} or m is None
        for m in (getattr(r, "methods", None) for r in c.app.routes)  # type: ignore[attr-defined]
        if getattr(r, "path", "").startswith("/api/")
    )
