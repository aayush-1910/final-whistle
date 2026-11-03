"""Tests for league rules, the table/tiebreaker engine, and the season simulator."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import permutations
from pathlib import Path

import numpy as np
import pytest

from app.domain.models import LeagueRules, Tiebreaker, Zone
from app.models.data import MatchRecord
from app.models.poisson import PoissonModel, PoissonParams
from app.simulations.domestic import SimulationError, simulate_league
from app.simulations.rules import RulesNotFoundError, load_rules
from app.simulations.table import rank_teams

T = Tiebreaker


def rules(tiebreakers: list[Tiebreaker], n: int = 4, **kw: object) -> LeagueRules:
    return LeagueRules(
        competition_code="TEST", season_start_year=2026, team_count=n, points_for_win=3,
        points_for_draw=1, tiebreakers=tuple(tiebreakers), **kw,  # type: ignore[arg-type]
    )  # fmt: skip


def rank(res: list[tuple[int, int, int, int]], r: LeagueRules, seed: int = 0) -> list[int]:
    teams = sorted({t for m in res for t in m[:2]})
    return rank_teams(teams, res, r, np.random.default_rng(seed))


# ---------------------------------------------------------------------------
# Rules files
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("code", "n"), [("EPL", 20), ("LA_LIGA", 20), ("BUNDESLIGA", 18), ("SERIE_A", 20)]
)
def test_2026_rules_load(code: str, n: int) -> None:
    r = load_rules(code, 2026)
    assert r.team_count == n and r.is_verified
    expected_quality = "primary" if code in ("EPL", "BUNDESLIGA") else "secondary"
    assert r.source_quality == expected_quality
    assert r.zone("champion") is not None and r.zone("relegation") is not None


def test_league_specific_rules() -> None:
    assert load_rules("LA_LIGA", 2026).tiebreakers[1] is T.HEAD_TO_HEAD_POINTS
    assert load_rules("SERIE_A", 2026).tiebreakers[1] is T.HEAD_TO_HEAD_POINTS
    assert load_rules("EPL", 2026).tiebreakers[1] is T.GOAL_DIFFERENCE
    assert load_rules("BUNDESLIGA", 2026).tiebreakers[1] is T.GOAL_DIFFERENCE
    assert load_rules("SERIE_A", 2026).playoff_positions == (1, 17)
    bl = load_rules("BUNDESLIGA", 2026)
    assert bl.zone("relegation_playoff") == Zone(
        "relegation_playoff", "Relegation play-off", 16, 16
    )


def test_missing_rules(tmp_path: Path) -> None:
    with pytest.raises(RulesNotFoundError):
        load_rules("EPL", 2026, base=tmp_path)


# ---------------------------------------------------------------------------
# Tiebreakers
# ---------------------------------------------------------------------------
def table(res: list[tuple[int, int, int, int]]) -> dict[int, tuple[int, int, int]]:
    """(points, goal difference, goals for) per team: lets tests assert their own premise."""
    out: dict[int, list[int]] = {}
    for h, a, hg, ag in res:
        for team, gf, ga in ((h, hg, ag), (a, ag, hg)):
            row = out.setdefault(team, [0, 0, 0])
            row[0] += 3 if gf > ga else 1 if gf == ga else 0
            row[1] += gf - ga
            row[2] += gf
    return {k: (v[0], v[1], v[2]) for k, v in out.items()}


# Teams 1 and 2 level on points (11).  1 has the far better goal difference;
# 2 won the head-to-head (4 pts to 1).
H2H_VS_GD = [
    (1, 2, 0, 1), (2, 1, 0, 0),
    (1, 3, 5, 0), (3, 1, 0, 5), (1, 4, 5, 0), (4, 1, 0, 0),
    (2, 3, 1, 0), (3, 2, 0, 1), (2, 4, 1, 1), (4, 2, 1, 0),
    (3, 4, 2, 0), (4, 3, 1, 1),
]  # fmt: skip


def test_scenario_premise() -> None:
    tb = table(H2H_VS_GD)
    assert tb[1][0] == tb[2][0] == 11
    assert tb[1][1] > tb[2][1]


def test_points_then_gd_league_uses_goal_difference() -> None:
    r = rank(H2H_VS_GD, rules([T.POINTS, T.GOAL_DIFFERENCE, T.GOALS_FOR, T.HEAD_TO_HEAD_POINTS]))
    assert r[:2] == [1, 2]


def test_head_to_head_first_league_uses_head_to_head() -> None:
    r = rank(H2H_VS_GD, rules([T.POINTS, T.HEAD_TO_HEAD_POINTS, T.GOAL_DIFFERENCE]))
    assert r[:2] == [2, 1]


# Teams 1, 2, 3 level on 6 points.  Their mini-league ranks them 1, 2, 3;
# overall goal difference ranks 3 first (a 5-0 win over team 4).
THREE_WAY = [
    (1, 2, 1, 0), (2, 1, 0, 0), (2, 3, 1, 0), (3, 2, 0, 0), (3, 1, 0, 0), (1, 3, 0, 0),
    (1, 4, 0, 1), (4, 1, 1, 0), (2, 4, 0, 0), (4, 2, 1, 0), (3, 4, 5, 0), (4, 3, 1, 0),
]  # fmt: skip


def test_three_way_head_to_head_mini_league() -> None:
    tb = table(THREE_WAY)
    assert tb[1][0] == tb[2][0] == tb[3][0] == 6 and tb[3][1] > tb[1][1]
    h2h = rules(
        [T.POINTS, T.HEAD_TO_HEAD_POINTS, T.HEAD_TO_HEAD_GOAL_DIFFERENCE, T.GOAL_DIFFERENCE]
    )
    assert rank(THREE_WAY, h2h) == [4, 1, 2, 3]
    gd_first = rules([T.POINTS, T.GOAL_DIFFERENCE, T.HEAD_TO_HEAD_POINTS])
    assert rank(THREE_WAY, gd_first)[:2] == [4, 3]


def test_bundesliga_head_to_head_away_goals() -> None:
    # 1 and 2 level on points, GD, GF and head-to-head points; 1 scored 3 away
    # goals in the head-to-head, 2 scored 1.
    res = [(1, 2, 0, 1), (2, 1, 2, 3), (1, 3, 1, 0), (3, 1, 0, 0), (2, 3, 1, 0), (3, 2, 0, 0)]
    tb = table(res)
    assert tb[1] == tb[2]
    r = rules([T.POINTS, T.GOAL_DIFFERENCE, T.GOALS_FOR, T.HEAD_TO_HEAD_POINTS,
               T.HEAD_TO_HEAD_AWAY_GOALS_FOR, T.AWAY_GOALS_FOR, T.PLAYOFF], n=3)  # fmt: skip
    assert {tuple(rank(res, r, seed=s)) for s in range(20)} == {(1, 2, 3)}


def test_complete_tie_is_random_but_seeded() -> None:
    res = [(1, 2, 1, 1), (2, 1, 1, 1)]
    r = rules([T.POINTS, T.GOAL_DIFFERENCE, T.PLAYOFF], n=2)
    outcomes = {tuple(rank(res, r, seed=s)) for s in range(40)}
    assert outcomes == {(1, 2), (2, 1)}
    assert rank(res, r, seed=7) == rank(res, r, seed=7)


def test_serie_a_style_playoff_overrides_head_to_head() -> None:
    # 1 and 2 level on 7 points; 1 won the head-to-head; a tie for 1st goes to a play-off.
    res = [(1, 2, 1, 0), (2, 1, 0, 0), (1, 3, 1, 0), (3, 1, 1, 0), (2, 3, 2, 0), (3, 2, 0, 1)]
    tb = table(res)
    assert tb[1][0] == tb[2][0] == 7
    with_playoff = rules([T.POINTS, T.HEAD_TO_HEAD_POINTS], n=3, playoff_positions=(1,))
    without = rules([T.POINTS, T.HEAD_TO_HEAD_POINTS], n=3)
    assert {rank(res, without, seed=s)[0] for s in range(40)} == {1}
    firsts = Counter(rank(res, with_playoff, seed=s)[0] for s in range(400))
    assert set(firsts) == {1, 2} and 150 < firsts[1] < 250


def test_playoff_not_triggered_without_points_tie() -> None:
    res = [(1, 2, 3, 0), (2, 1, 0, 3)]
    r = rules([T.POINTS, T.GOAL_DIFFERENCE], n=2, playoff_positions=(1,))
    assert {tuple(rank(res, r, seed=s)) for s in range(30)} == {(1, 2)}


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------
T0 = datetime(2026, 8, 1, tzinfo=UTC)
AS_OF = T0 + timedelta(days=30)


def model(strength: dict[int, float] | None = None) -> PoissonModel:
    s = strength or {}
    teams = [1, 2, 3, 4]
    return PoissonModel(
        params=PoissonParams(), as_of=AS_OF, mu=0.3, home_advantage=0.2,
        attack={t: s.get(t, 0.0) for t in teams}, defence={t: s.get(t, 0.0) for t in teams},
        matches_used=100, converged=True,
    )  # fmt: skip


def season(
    played: dict[tuple[int, int], tuple[int, int]], drop: set[tuple[int, int]] = frozenset()
) -> list[MatchRecord]:  # type: ignore[assignment]
    out = []
    for i, (h, a) in enumerate(permutations([1, 2, 3, 4], 2)):
        if (h, a) in drop:
            continue
        if (h, a) in played:
            hg, ag = played[(h, a)]
            out.append(MatchRecord(i, T0 + timedelta(days=i), "TEST", 2026, h, a, hg, ag))
        else:
            out.append(
                MatchRecord(i, AS_OF + timedelta(days=i + 1), "TEST", 2026, h, a, None, None)
            )
    return out


R4 = rules(
    [T.POINTS, T.GOAL_DIFFERENCE, T.GOALS_FOR, T.PLAYOFF],
    zones=(Zone("champion", "C", 1, 1), Zone("relegation", "R", 4, 4)),
)


def test_finished_season_is_deterministic() -> None:
    results = {p: (2, 0) if p[0] < p[1] else (0, 0) for p in permutations([1, 2, 3, 4], 2)}
    f = simulate_league(season(results), "TEST", 2026, model(), R4, AS_OF, n_sims=200, seed=1)
    assert f.matches == []
    assert [f.prob(t, t) for t in (1, 2, 3, 4)] == [1.0, 1.0, 1.0, 1.0]
    assert f.zone_probs["relegation"][4] == 1.0


def test_probabilities_are_distributions_and_reproducible() -> None:
    m = model({1: 0.5, 4: -0.5})
    a = simulate_league(season({}), "TEST", 2026, m, R4, AS_OF, n_sims=4000, seed=3)
    b = simulate_league(season({}), "TEST", 2026, m, R4, AS_OF, n_sims=4000, seed=3)
    assert np.allclose(a.position_probs.sum(axis=0), 1) and np.allclose(
        a.position_probs.sum(axis=1), 1
    )
    assert np.array_equal(a.position_probs, b.position_probs)
    assert a.title_probs[1] > a.title_probs[2] > a.title_probs[4]
    assert sum(a.title_probs.values()) == pytest.approx(1)
    for mf in a.matches:
        assert mf.p_home + mf.p_draw + mf.p_away == pytest.approx(1)


def test_converges_across_seeds() -> None:
    m = model({1: 0.3})
    a = simulate_league(season({}), "TEST", 2026, m, R4, AS_OF, n_sims=20000, seed=1)
    b = simulate_league(season({}), "TEST", 2026, m, R4, AS_OF, n_sims=20000, seed=2)
    assert np.abs(a.position_probs - b.position_probs).max() < 0.02


def test_results_after_as_of_are_not_used() -> None:
    late = [MatchRecord(99, AS_OF + timedelta(days=1), "TEST", 2026, 1, 2, 9, 0)]
    recs = [r for r in season({}) if (r.home_team_id, r.away_team_id) != (1, 2)] + late
    f = simulate_league(recs, "TEST", 2026, model(), R4, AS_OF, n_sims=100, seed=0)
    assert f.completed_matches == 0 and len(f.matches) == 12


def test_missing_fixture_is_added_and_reported() -> None:
    f = simulate_league(season({}, drop={(3, 1)}), "TEST", 2026, model(), R4, AS_OF, n_sims=50)
    assert f.added_fixtures == [(3, 1)] and len(f.matches) == 12
    assert any("missing" in n for n in f.notes)


def test_duplicate_fixture_rejected() -> None:
    recs = season({})
    recs.append(MatchRecord(500, AS_OF + timedelta(days=90), "TEST", 2026, 1, 2, None, None))
    with pytest.raises(SimulationError, match="Duplicate"):
        simulate_league(recs, "TEST", 2026, model(), R4, AS_OF, n_sims=10)


def test_wrong_team_count_rejected() -> None:
    with pytest.raises(SimulationError, match="teams"):
        simulate_league(season({}), "TEST", 2026, model(), rules([T.POINTS], n=6), AS_OF, n_sims=10)


def test_model_fitted_after_as_of_rejected() -> None:
    with pytest.raises(SimulationError, match="leakage"):
        simulate_league(season({}), "TEST", 2026, model(), R4, AS_OF - timedelta(days=1), n_sims=10)


def test_current_points_from_completed_only() -> None:
    f = simulate_league(
        season({(1, 2): (1, 0), (3, 4): (2, 2)}), "TEST", 2026, model(), R4, AS_OF, n_sims=10
    )
    assert f.current_points == {1: 3, 2: 0, 3: 1, 4: 1}
    assert f.played == {1: 1, 2: 1, 3: 1, 4: 1}


def test_bundesliga_head_to_head_is_aggregate_score_not_points() -> None:
    # DFL SpOL §2 Nr. 3 c) 3): "Gesamtergebnis aus Hin- und Rückspiel im direkten Vergleich".
    # A beat B 1-0, B beat A 3-0: equal head-to-head points, but B wins on aggregate (3-1).
    res = [(1, 2, 1, 0), (2, 1, 3, 0)]
    aggregate = rules([T.POINTS, T.HEAD_TO_HEAD_GOAL_DIFFERENCE, T.PLAYOFF], n=2)
    points_only = rules([T.POINTS, T.HEAD_TO_HEAD_POINTS, T.PLAYOFF], n=2)
    assert {tuple(rank(res, aggregate, seed=s)) for s in range(20)} == {(2, 1)}
    assert {tuple(rank(res, points_only, seed=s)) for s in range(40)} == {(1, 2), (2, 1)}
