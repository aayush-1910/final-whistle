"""
Regression tests against REAL final tables (read-only queries on the live database).

Run with:  RUN_DB_TESTS=1 python -m pytest tests/integration
Requires the 2023-2025 seasons to have been ingested.

- Goal-difference-first leagues (EPL, Bundesliga) and the UCL league phase must
  match the provider's final standings exactly.
- football-data.org orders level clubs by goal difference even in head-to-head
  leagues (docs/known-data-issues.md #5), so for La Liga and Serie A we check
  against published final tables (Wikipedia, read 2026-11-03), including a
  3-club head-to-head mini-league (Getafe / Espanyol / Alaves, La Liga 2024/25).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import numpy as np
import psycopg
import pytest

from app.database.connection import connect
from app.simulations.rules import load_rules
from app.simulations.table import rank_teams

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to run database tests"
)


@pytest.fixture(scope="module")
def conn() -> Iterator[psycopg.Connection[Any]]:
    c = connect()
    try:
        yield c
    finally:
        c.close()


def our_order(conn: psycopg.Connection[Any], comp: str, year: int) -> list[int]:
    stage = "league_stage" if comp == "UCL" else "regular_season"
    res = conn.execute(
        """select f.home_team_id, f.away_team_id, f.home_score, f.away_score from fixtures f
             join seasons s on s.id = f.season_id join competitions c on c.id = s.competition_id
            where c.code = %s and s.start_year = %s and f.stage = %s
              and f.status in ('finished', 'awarded')""",
        (comp, year, stage),
    ).fetchall()
    if not res:
        pytest.skip(f"{comp} {year} not ingested")
    rules = replace(load_rules(comp, 2026), season_start_year=year)
    teams = sorted({t for r in res for t in r[:2]})
    orders = {tuple(rank_teams(teams, res, rules, np.random.default_rng(s))) for s in range(5)}
    assert len(orders) == 1, "final table should not need a random tiebreak"
    return list(orders.pop())


def provider_order(conn: psycopg.Connection[Any], comp: str, year: int) -> list[int]:
    return [
        r[0]
        for r in conn.execute(
            """select r.team_id from standings_rows r where r.snapshot_id = (
                 select max(ss.id) from standings_snapshots ss join seasons s on s.id = ss.season_id
                   join competitions c on c.id = s.competition_id
                  where c.code = %s and s.start_year = %s)
               order by r.position""",
            (comp, year),
        )
    ]


def names(conn: psycopg.Connection[Any], ids: list[int]) -> list[str]:
    lookup = dict(conn.execute("select id, coalesce(short_name, name) from teams").fetchall())
    return [lookup[i] for i in ids]


@pytest.mark.parametrize(
    ("comp", "year"),
    [(c, y) for c in ("EPL", "BUNDESLIGA") for y in (2023, 2024, 2025)] + [("UCL", 2025)],
)
def test_matches_provider_table(conn: psycopg.Connection[Any], comp: str, year: int) -> None:
    assert our_order(conn, comp, year) == provider_order(conn, comp, year)


def test_la_liga_2024_head_to_head(conn: psycopg.Connection[Any]) -> None:
    # Published final table, positions 7-18.
    expected = ["Celta", "Rayo Vallecano", "Osasuna", "Mallorca", "Real Sociedad", "Valencia",
                "Getafe", "Espanyol", "Alavés", "Girona", "Sevilla FC", "Leganés"]  # fmt: skip
    assert names(conn, our_order(conn, "LA_LIGA", 2024))[6:18] == expected


def test_serie_a_2023_head_to_head(conn: psycopg.Connection[Any]) -> None:
    # Published final table, positions 8-18.
    expected = ["Fiorentina", "Torino", "Napoli", "Genoa", "Monza", "Verona", "Lecce",
                "Udinese", "Cagliari", "Empoli", "Frosinone"]  # fmt: skip
    assert names(conn, our_order(conn, "SERIE_A", 2023))[7:18] == expected


def test_ucl_2025_knockout_replay(conn: psycopg.Connection[Any]) -> None:
    """Replay the real 2025/26 knockout phase round by round (each round revealed only
    after the previous one ended).  Every state must simulate, keep 16/8/4/2/1 clubs per
    round, and after the final the real winner must have probability 1."""
    from datetime import timedelta

    from app.database import repository as repo
    from app.domain.models import Stage
    from app.models import config
    from app.models.data import load_match_records
    from app.models.poisson import fit_poisson
    from app.simulations.ucl import KNOCKOUT_STAGES, round_sanity, simulate_ucl

    recs = load_match_records(conn)
    ko = [
        f
        for f in repo.load_fixtures(conn, repo.season_id(conn, "UCL", 2025))
        if f.stage in KNOCKOUT_STAGES
    ]
    if len(ko) != 45:
        pytest.skip("UCL 2025/26 knockout phase not fully ingested")
    rules = replace(load_rules("UCL", 2026), season_start_year=2025)
    order = [Stage.PLAYOFFS, Stage.LAST_16, Stage.QUARTER_FINALS, Stage.SEMI_FINALS, Stage.FINAL]
    league_end = max(
        r.kickoff_utc
        for r in recs
        if r.competition == "UCL" and r.season_year == 2025 and r.stage == "league_stage"
    )
    last = {s: max(f.kickoff_utc for f in ko if f.stage is s) for s in order}  # type: ignore[type-var]
    first = {s: min(f.kickoff_utc for f in ko if f.stage is s) for s in order}  # type: ignore[type-var]
    revealed_after = {
        Stage.PLAYOFFS: league_end,
        **{b: last[a] for a, b in zip(order, order[1:], strict=False)},
    }
    final = next(f for f in ko if f.stage is Stage.FINAL)
    champion = final.winner_team_id or final.shootout_winner_team_id

    for as_of in [first[s] - timedelta(hours=3) for s in order] + [
        last[Stage.FINAL] + timedelta(days=1)
    ]:
        known = [f for f in ko if revealed_after[f.stage] < as_of]
        model = fit_poisson(recs, as_of, config.POISSON)
        f = simulate_ucl(recs, 2025, model, rules, as_of, n_sims=300, seed=1, knockout=known)
        assert round_sanity(f) == pytest.approx(
            {"round_of_16": 16, "quarter_finals": 8, "semi_finals": 4, "final": 2, "winner": 1}
        )
    assert f.round_probs["winner"][champion] == 1.0
