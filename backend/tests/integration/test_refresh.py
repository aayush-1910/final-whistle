"""
The scheduled refresh end to end against a throwaway schema: import (one
competition failing), forecast, publish through the gates, and a second run
that correctly does nothing.

Run with:  RUN_DB_TESTS=1 python -m pytest tests/integration
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from app.database.connection import connect
from app.database.forecasts import save_backtest
from app.database.migrate import migrate
from app.domain.models import LeagueRules, Tiebreaker, Zone
from app.ingestion.service import IngestionResult, ingest_season
from app.models import config
from app.models.poisson import PoissonModel, PoissonParams
from app.services import refresh as refresh_mod
from app.simulations.domestic import simulate_league
from tests.integration.test_database import FakeAPI

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to run database tests"
)


@pytest.fixture()
def db() -> Iterator[psycopg.Connection[Any]]:
    schema = f"fw_test_{uuid.uuid4().hex[:10]}"
    conn = connect()
    conn.execute(f"create schema {schema}")
    conn.execute(f"set search_path to {schema}")
    try:
        migrate(conn)
        save_backtest(
            conn,
            kind="match",
            model_name="x",
            model_version=config.MODEL_VERSION,
            params={},
            tuning_window={},
            test_window={},
            metrics={},
            code_version=None,
        )
        save_backtest(conn, kind="season", model_name="x", model_version=config.MODEL_VERSION,
                      params={}, tuning_window={}, test_window={}, metrics={}, code_version=None)  # fmt: skip
        yield conn
    finally:
        conn.execute(f"drop schema if exists {schema} cascade")
        conn.close()


def test_refresh_end_to_end(db: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    api = FakeAPI()
    rules = LeagueRules("EPL", 2026, 3, 3, 1, (Tiebreaker.POINTS, Tiebreaker.PLAYOFF),
                        zones=(Zone("champion", "Champions", 1, 1),))  # fmt: skip

    # A 3-team toy league: real EPL rules expect 20 clubs, so substitute small rules and a
    # fixed model; everything else (import, decisions, storage, gates) is the real code.
    def fake_fit(records: Any, as_of: datetime, params: Any) -> PoissonModel:
        return PoissonModel(PoissonParams(), as_of, 0.3, 0.2, {}, {}, 1, True)

    def fake_sim(conn: Any, records: Any, model: Any, comp: str, season: int, as_of: datetime,
                 **kw: Any) -> Any:  # fmt: skip
        return simulate_league(records, comp, season, model, rules, as_of, n_sims=200, seed=1), (
            rules
        )

    monkeypatch.setattr(refresh_mod, "fit_poisson", fake_fit)
    monkeypatch.setattr(refresh_mod, "simulate_competition", fake_sim)

    with api.client() as client:

        def ingest(code: str, season: int) -> IngestionResult:
            if code == "LA_LIGA":
                raise ConnectionError("provider unreachable")
            return ingest_season(db, client, code, season, raw_dir=None)

        first = refresh_mod.refresh(db, ingest, competitions=["EPL", "LA_LIGA"], n_sims=200)

    steps = {(s.competition, s.step): s for s in first.steps}
    assert steps[("EPL", "import")].status == "ok"
    assert steps[("LA_LIGA", "import")].status == "failed"
    assert "provider unreachable" in steps[("LA_LIGA", "import")].detail
    assert steps[("LA_LIGA", "forecast")].status == "skipped"
    assert steps[("EPL", "forecast")].status == "ok"
    pub = steps[("EPL", "publish")]
    assert pub.status == "ok", pub.detail
    assert db.execute(
        "select is_published from model_runs where id = %s", (pub.run_id,)
    ).fetchone() == (True,)
    assert first.failed  # one import failed -> the scheduler must see a failure
    assert first.to_dict()["steps"][0]["competition"] == "EPL"

    # Nothing changed since: no new forecast, nothing failed.
    second = refresh_mod.refresh(db, None, competitions=["EPL"],
                                 now=lambda: datetime.now(tz=UTC))  # fmt: skip
    assert [(s.step, s.status) for s in second.steps] == [
        ("import", "skipped"),
        ("forecast", "skipped"),
    ]
    assert not second.failed
    assert db.execute("select count(*) from model_runs").fetchone() == (1,)
