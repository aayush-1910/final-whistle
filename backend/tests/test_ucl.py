"""Tests for the Champions League simulator: bracket rules (Art. 19-22) and invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.models.data import MatchRecord
from app.models.poisson import PoissonModel, PoissonParams
from app.simulations.domestic import SimulationError
from app.simulations.rules import load_rules
from app.simulations.ucl import (
    PLAYOFF_GROUPS,
    UnsupportedStateError,
    _Knockout,
    round_sanity,
    simulate_ucl,
)

T0 = datetime(2026, 9, 1, tzinfo=UTC)
AS_OF = T0 + timedelta(days=60)
TEAMS = list(range(1, 37))  # club id == final league-phase position in the bracket audit
RULES = load_rules("UCL", 2026)


def model(seed: int = 0, spread: float = 0.3) -> PoissonModel:
    rng = np.random.default_rng(seed)
    strength = {t: float(rng.normal(0, spread)) for t in TEAMS}
    return PoissonModel(PoissonParams(), AS_OF, 0.3, 0.2, strength, dict(strength), 1000, True)


# ---------------------------------------------------------------------------
# Bracket audit: every simulated knockout phase must obey the regulations
# ---------------------------------------------------------------------------
SEED_PAIR = {p: pair for pair in ((1, 2), (3, 4), (5, 6), (7, 8)) for p in pair}
PLAYOFF_TO_R16 = {s: r16 for seeded, unseeded, r16 in PLAYOFF_GROUPS for s in (*seeded, *unseeded)}


def audit(trace: list[tuple[str, int, int, int]]) -> None:
    by_round: dict[str, list[tuple[int, int, int]]] = {}
    for rnd, first, second, winner in trace:
        by_round.setdefault(rnd, []).append((first, second, winner))
    assert [
        len(by_round[r])
        for r in ("playoffs", "round_of_16", "quarter_finals", "semi_finals", "final")
    ] == [8, 8, 4, 2, 1]

    # Art. 19.02: 9/10 v 23/24, 11/12 v 21/22, 13/14 v 19/20, 15/16 v 17/18; seed hosts 2nd leg.
    po_winner_group: dict[int, tuple[int, int]] = {}
    for first, second, winner in by_round["playoffs"]:
        assert 17 <= first <= 24 and 9 <= second <= 16
        assert PLAYOFF_TO_R16[first] == PLAYOFF_TO_R16[second]
        assert winner in (first, second)
        po_winner_group[winner] = PLAYOFF_TO_R16[second]
    assert sorted(s for _, s, _ in by_round["playoffs"]) == list(range(9, 17))

    # Art. 19.03: seeds 1-8 host the 2nd leg against a play-off winner from the matching group.
    slot_of: dict[int, tuple[int, int]] = {}
    for first, second, winner in by_round["round_of_16"]:
        assert 1 <= second <= 8 and first in po_winner_group
        assert po_winner_group[first] == SEED_PAIR[second]
        slot_of[winner] = SEED_PAIR[second]  # winner takes over the seed's slot
    assert sorted(s for _, s, _ in by_round["round_of_16"]) == list(range(1, 9))

    # Art. 19.04: QF = [1/2 slot v 7/8 slot] or [3/4 slot v 5/6 slot]; 1/2 or 3/4 slot hosts 2nd leg.
    qf_winner_slot: dict[int, tuple[int, int]] = {}
    for first, second, winner in by_round["quarter_finals"]:
        pair = {slot_of[first], slot_of[second]}
        assert pair in ({(1, 2), (7, 8)}, {(3, 4), (5, 6)})
        assert slot_of[second] in ((1, 2), (3, 4))
        qf_winner_slot[winner] = slot_of[second]

    # SF: winner of [1/2 v 7/8] (hosts 2nd leg) v winner of [3/4 v 5/6].
    finalists = set()
    for first, second, winner in by_round["semi_finals"]:
        assert qf_winner_slot[second] == (1, 2) and qf_winner_slot[first] == (3, 4)
        finalists.add(winner)

    # Each half holds exactly one club from every seeded pair: 1 and 2 can only meet in the final.
    halves = []
    r16 = by_round["round_of_16"]
    qf = by_round["quarter_finals"]
    for first, second, _ in by_round["semi_finals"]:
        qf_ties = [t for t in qf if t[2] in (first, second)]
        qf_clubs = {c for t in qf_ties for c in t[:2]}
        seeds = {s for f, s, w in r16 if w in qf_clubs}
        halves.append(seeds)
    assert len(halves) == 2 and halves[0].isdisjoint(halves[1])
    for half in halves:
        assert sorted(SEED_PAIR[s] for s in half) == [(1, 2), (3, 4), (5, 6), (7, 8)]

    (_, _, champion), = by_round["final"]  # fmt: skip
    assert set(by_round["final"][0][:2]) == finalists and champion in finalists


def test_bracket_obeys_regulations_in_every_simulation() -> None:
    m = model()
    rng = np.random.default_rng(42)
    for _ in range(2000):
        trace: list[tuple[str, int, int, int]] = []
        ko = _Knockout(m, rng, trace)
        reached = ko.run(TEAMS)
        audit(trace)
        assert [len(reached[r]) for r in reached] == [16, 8, 4, 2, 1]
        assert set(TEAMS[:8]) <= set(reached["round_of_16"])
        assert not set(TEAMS[24:]) & set(reached["round_of_16"])


def test_both_pairings_of_a_seeded_pair_occur() -> None:
    """The draw decides which half 1 and 2 go to, and which play-off winner meets which seed."""
    m = model()
    rng = np.random.default_rng(1)
    opponents_of_1: set[int] = set()
    for _ in range(400):
        trace: list[tuple[str, int, int, int]] = []
        _Knockout(m, rng, trace).run(TEAMS)
        opponents_of_1 |= {f for r, f, s, _ in trace if r == "round_of_16" and s == 1}
    assert opponents_of_1 <= set(range(15, 19)) and len(opponents_of_1) >= 3


def test_much_stronger_club_usually_wins_a_tie() -> None:
    strong = PoissonModel(
        PoissonParams(), AS_OF, 0.3, 0.2, {1: 1.0, 2: -1.0}, {1: 1.0, 2: -1.0}, 10, True
    )
    ko = _Knockout(strong, np.random.default_rng(0))
    wins = sum(ko.two_legs("x", 2, 1) == 1 for _ in range(2000))
    assert wins > 1800


# ---------------------------------------------------------------------------
# Full simulation on a synthetic league phase
# ---------------------------------------------------------------------------
def league_phase(played_until: int = 0) -> list[MatchRecord]:
    """36 clubs on a circle: club i hosts i+1..i+4 -> 8 opponents, 4 home + 4 away, 144 matches.
    The first ``played_until`` matches get varied, seeded random scores."""
    rng = np.random.default_rng(123)
    out = []
    n = 0
    for i in range(36):
        for k in range(1, 5):
            h, a = TEAMS[i], TEAMS[(i + k) % 36]
            played = n < played_until
            hg, ag = (int(rng.poisson(1.6)), int(rng.poisson(1.2))) if played else (None, None)
            out.append(MatchRecord(n, (T0 if played else AS_OF) + timedelta(hours=n), "UCL", 2026,
                                   h, a, hg, ag))  # fmt: skip
            n += 1
    return out


def test_simulation_invariants_and_reproducibility() -> None:
    recs = league_phase(played_until=54)
    a = simulate_ucl(recs, 2026, model(3), RULES, AS_OF, n_sims=1500, seed=9)
    b = simulate_ucl(recs, 2026, model(3), RULES, AS_OF, n_sims=1500, seed=9)
    assert round_sanity(a) == pytest.approx(
        {"round_of_16": 16, "quarter_finals": 8, "semi_finals": 4, "final": 2, "winner": 1}
    )
    assert np.allclose(a.position_probs.sum(0), 1) and np.allclose(a.position_probs.sum(1), 1)
    assert np.array_equal(a.position_probs, b.position_probs) and a.round_probs == b.round_probs
    assert a.completed_matches == 54 and len(a.matches) == 90
    for t in TEAMS:
        r = a.round_probs
        assert (
            r["round_of_16"][t]
            >= r["quarter_finals"][t]
            >= r["semi_finals"][t]
            >= r["final"][t]
            >= r["winner"][t]
        )
        assert r["round_of_16"][t] >= a.zone_probs["round_of_16"][t] - 1e-12


def test_finished_league_phase_fixes_positions() -> None:
    recs = league_phase(played_until=144)
    f = simulate_ucl(recs, 2026, model(), RULES, AS_OF, n_sims=300, seed=1)
    assert f.matches == []
    # Varied scores separate every club before the random criteria are reached.
    assert set(np.unique(f.position_probs)) <= {0.0, 1.0}
    assert sum(f.zone_probs["round_of_16"].values()) == pytest.approx(8)


def test_stronger_club_more_likely_to_win() -> None:
    strengths = {t: (0.8 if t == 5 else 0.0) for t in TEAMS}
    m = PoissonModel(PoissonParams(), AS_OF, 0.3, 0.2, strengths, dict(strengths), 1000, True)
    f = simulate_ucl(league_phase(), 2026, m, RULES, AS_OF, n_sims=1500, seed=2)
    w = f.round_probs["winner"]
    assert w[5] == max(w.values()) and w[5] > 5 / 36


def test_knockout_fixtures_present_is_unsupported() -> None:
    recs = league_phase() + [
        MatchRecord(999, AS_OF + timedelta(days=100), "UCL", 2026, 1, 2, None, None)
    ]
    with pytest.raises(UnsupportedStateError):
        simulate_ucl(recs, 2026, model(), RULES, AS_OF, n_sims=10)


def test_model_from_the_future_rejected() -> None:
    with pytest.raises(SimulationError, match="leakage"):
        simulate_ucl(league_phase(), 2026, model(), RULES, AS_OF - timedelta(days=1), n_sims=10)
