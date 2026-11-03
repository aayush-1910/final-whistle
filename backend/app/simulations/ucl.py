"""
UEFA Champions League 2026/27 simulation: league phase + knockout phase.

Source: Regulations of the UEFA Champions League 2026/27 (in force 29 July 2026),
https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27-Online

League phase (Art. 17-18)
  36 clubs, 8 matches each, one table.  Tiebreakers from rules/2026/UCL.json.
  1-8 -> round of 16, 9-24 -> knockout phase play-offs, 25-36 eliminated.

Knockout phase play-offs (Art. 19.02)
  Seeded pairs 9/10, 11/12, 13/14, 15/16 meet unseeded pairs 23/24, 21/22,
  19/20, 17/18 respectively; which member meets which is drawn.  Seeded club
  hosts the second leg.

Round of 16 (Art. 19.03, Annex B)
  Seeded pairs 1/2, 3/4, 5/6, 7/8.  The two winners of the play-off ties
  involving 15/16 meet 1/2; 13/14 -> 3/4; 11/12 -> 5/6; 9/10 -> 7/8
  (which winner meets which seed is drawn).  Each seeded pair is split across
  the two halves of the bracket by draw.  Seeded club hosts the second leg.
  Annex B is published only as an image; this mapping comes from UEFA's draw
  explainers and matches the actual 2024/25 draw.

Quarter-finals / semi-finals (Art. 19.04)
  Fixed bracket in each half: [1/2 slot v 7/8 slot] and [3/4 slot v 5/6 slot]
  in the quarter-finals, their winners in the semi-final.  The club that
  eliminates a seed takes over its slot (seeding is not recalculated).  The
  1-4 slot holder hosts the quarter-final second leg; the 1/2 slot holder
  hosts the semi-final second leg.

Ties (Art. 20-22)
  Two legs, aggregate goals, no away-goals rule; if level, 30 minutes of extra
  time at the end of the second leg, then penalties.  Final: one match at a
  neutral venue, extra time, penalties.

Modelling approximations (documented in docs/model-methodology.md)
  - Extra-time goals: Poisson with the match's expected goals scaled by 30/90.
  - Penalty shoot-outs: 50/50.
  - Disciplinary points and club coefficient (last league-phase tiebreakers)
    are not in our data: a tie reaching them is broken by a seeded random draw.
  - Only supported BEFORE the knockout phase starts (no knockout fixtures in
    the data yet).  Conditioning on the real draws is a follow-up.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.domain.models import LeagueRules
from app.models.data import MatchRecord
from app.models.poisson import PoissonModel, outcome_probabilities
from app.simulations.domestic import MatchForecast, SeasonForecast, SimulationError, _points
from app.simulations.table import Result, TeamTotals, rank_from_totals

LEAGUE_PHASE_TEAMS = 36
MATCHES_PER_TEAM = 8
# (seeded positions, unseeded positions) for the knockout phase play-offs, and the
# round-of-16 seeded pair their winners meet (Art. 19.02-19.03, Annex B).
PLAYOFF_GROUPS: tuple[tuple[tuple[int, int], tuple[int, int], tuple[int, int]], ...] = (
    ((9, 10), (23, 24), (7, 8)),
    ((11, 12), (21, 22), (5, 6)),
    ((13, 14), (19, 20), (3, 4)),
    ((15, 16), (17, 18), (1, 2)),
)
ROUNDS = ("round_of_16", "quarter_finals", "semi_finals", "final", "winner")
EXTRA_TIME_FRACTION = 30 / 90


class UnsupportedStateError(SimulationError):
    pass


@dataclass
class UCLForecast(SeasonForecast):
    # Probability of reaching each round (playing in it); "winner" = winning the final.
    round_probs: dict[str, dict[int, float]] = field(default_factory=dict)


class _Knockout:
    """Simulates the knockout phase for one league-phase ranking."""

    def __init__(
        self,
        model: PoissonModel,
        rng: np.random.Generator,
        trace: list[tuple[str, int, int, int]] | None = None,
    ):
        self.model = model
        self.rng = rng
        self._lam: dict[tuple[int, int, bool], tuple[float, float]] = {}
        # When given, every tie is appended as (round, first-leg home, second-leg home,
        # winner); for the final, (round, club, club, winner).  Used by tests to audit
        # the bracket against the regulations.
        self.trace = trace

    def lam(self, home: int, away: int, neutral: bool = False) -> tuple[float, float]:
        key = (home, away, neutral)
        if key not in self._lam:
            self._lam[key] = self.model.expected_goals(home, away, neutral=neutral)
        return self._lam[key]

    def _goals(
        self, home: int, away: int, scale: float = 1.0, neutral: bool = False
    ) -> tuple[int, int]:
        lh, la = self.lam(home, away, neutral)
        return int(self.rng.poisson(lh * scale)), int(self.rng.poisson(la * scale))

    def _after_draw(self, home: int, away: int, neutral: bool) -> int:
        """Extra time, then penalties.  Returns the winner."""
        eh, ea = self._goals(home, away, EXTRA_TIME_FRACTION, neutral)
        if eh != ea:
            return home if eh > ea else away
        return home if self.rng.random() < 0.5 else away

    def two_legs(self, rnd: str, first_leg_home: int, second_leg_home: int) -> int:
        a1, b1 = self._goals(first_leg_home, second_leg_home)
        b2, a2 = self._goals(second_leg_home, first_leg_home)
        agg_a, agg_b = a1 + a2, b1 + b2  # a = first-leg home club
        if agg_a != agg_b:
            winner = first_leg_home if agg_a > agg_b else second_leg_home
        else:
            winner = self._after_draw(second_leg_home, first_leg_home, neutral=False)
        if self.trace is not None:
            self.trace.append((rnd, first_leg_home, second_leg_home, winner))
        return winner

    def final(self, a: int, b: int) -> int:
        ga, gb = self._goals(a, b, neutral=True)
        winner = (a if ga > gb else b) if ga != gb else self._after_draw(a, b, neutral=True)
        if self.trace is not None:
            self.trace.append(("final", a, b, winner))
        return winner

    def run(self, ranking: Sequence[int]) -> dict[str, list[int]]:
        """``ranking[i]`` is the club in position i+1.  Returns clubs reaching each round."""
        pos = {p: ranking[p - 1] for p in range(1, LEAGUE_PHASE_TEAMS + 1)}
        rng = self.rng
        reached: dict[str, list[int]] = {r: [] for r in ROUNDS}

        # Play-offs -> round of 16 opponents for each seeded pair
        r16_opponents: dict[tuple[int, int], list[int]] = {}
        for seeded, unseeded, r16_pair in PLAYOFF_GROUPS:
            uns = list(unseeded)
            rng.shuffle(uns)
            winners = [
                self.two_legs("playoffs", pos[u], pos[s]) for s, u in zip(seeded, uns, strict=True)
            ]
            rng.shuffle(winners)  # which winner meets which seed is drawn
            r16_opponents[r16_pair] = winners

        # Split each seeded pair across the two halves (silver = 0, blue = 1)
        halves: list[dict[tuple[int, int], tuple[int, int]]] = [{}, {}]  # pair -> (seed pos, opp)
        for pair in ((1, 2), (3, 4), (5, 6), (7, 8)):
            seeds = list(pair)
            rng.shuffle(seeds)
            for side, (seed, opp) in enumerate(zip(seeds, r16_opponents[pair], strict=True)):
                halves[side][pair] = (seed, opp)

        semi_finalists: list[int] = []
        for half in halves:
            slot: dict[tuple[int, int], int] = {}  # slot -> current holder
            for pair, (seed, opp) in half.items():
                club = pos[seed]
                reached["round_of_16"] += [club, opp]
                slot[pair] = self.two_legs("round_of_16", opp, club)  # seed hosts 2nd leg
            qf1 = slot[(1, 2)], slot[(7, 8)]
            qf2 = slot[(3, 4)], slot[(5, 6)]
            reached["quarter_finals"] += [*qf1, *qf2]
            w1 = self.two_legs("quarter_finals", qf1[1], qf1[0])  # 1/2 slot holder hosts 2nd leg
            w2 = self.two_legs("quarter_finals", qf2[1], qf2[0])  # 3/4 slot holder hosts 2nd leg
            reached["semi_finals"] += [w1, w2]
            semi_finalists.append(
                self.two_legs("semi_finals", w2, w1)
            )  # 1/2-slot side hosts 2nd leg
        reached["final"] += semi_finalists
        reached["winner"].append(self.final(*semi_finalists))
        return reached


def simulate_ucl(
    records: Sequence[MatchRecord],
    season_year: int,
    model: PoissonModel,
    rules: LeagueRules,
    as_of: datetime,
    *,
    n_sims: int = 10_000,
    seed: int = 0,
) -> UCLForecast:
    if model.as_of > as_of:
        raise SimulationError("Model was fitted with a later cutoff than as_of (leakage)")
    if (rules.competition_code, rules.season_start_year) != ("UCL", season_year):
        raise SimulationError("Rules do not match UCL / season")

    season = [r for r in records if r.competition == "UCL" and r.season_year == season_year]
    # Knockout fixtures (anything not in the league phase) are identified by count:
    # the league phase is exactly 36 * 8 / 2 = 144 matches.
    teams = sorted({t for r in season for t in (r.home_team_id, r.away_team_id)})
    games = Counter(t for r in season for t in (r.home_team_id, r.away_team_id))
    if (
        len(teams) != LEAGUE_PHASE_TEAMS
        or len(season) != LEAGUE_PHASE_TEAMS * MATCHES_PER_TEAM // 2
    ):
        raise UnsupportedStateError(
            f"UCL {season_year}: expected exactly the 144 league-phase fixtures for 36 clubs, "
            f"found {len(season)} fixtures / {len(teams)} clubs. Simulating after knockout "
            "fixtures are published (i.e. conditioning on the real draws) is not implemented yet."
        )
    if any(games[t] != MATCHES_PER_TEAM for t in teams):
        raise SimulationError("Each club must have exactly 8 league-phase fixtures")
    if len({frozenset((r.home_team_id, r.away_team_id)) for r in season}) != len(season):
        raise SimulationError("A pair of clubs meets twice in the league phase")

    idx = {t: i for i, t in enumerate(teams)}
    n_t = len(teams)
    completed = [r for r in season if r.is_played and r.kickoff_utc < as_of]
    remaining = [r for r in season if not (r.is_played and r.kickoff_utc < as_of)]
    notes = []
    unknown = [t for t in teams if not model.knows(t)]
    if unknown:
        notes.append(
            f"{len(unknown)} club(s) have no model history and are treated as average: {unknown}"
        )

    # Opponent matrix (each club's 8 opponents) for Art. 18.01 f-h.
    opp = np.zeros((n_t, n_t), dtype=np.int64)
    for r in season:
        opp[idx[r.home_team_id], idx[r.away_team_id]] += 1
        opp[idx[r.away_team_id], idx[r.home_team_id]] += 1

    # All league-phase matches as columns: completed are constant, remaining sampled.
    rng = np.random.default_rng(seed)
    all_m = completed + remaining
    n_c = len(completed)
    lam = np.array(
        [model.expected_goals(r.home_team_id, r.away_team_id) for r in remaining]
    ).reshape(-1, 2)
    gh = np.empty((n_sims, len(all_m)), dtype=np.int64)
    ga = np.empty_like(gh)
    gh[:, :n_c] = np.array([int(r.home_goals or 0) for r in completed], dtype=np.int64)
    ga[:, :n_c] = np.array([int(r.away_goals or 0) for r in completed], dtype=np.int64)
    if remaining:
        gh[:, n_c:] = rng.poisson(lam[:, 0], size=(n_sims, len(remaining)))
        ga[:, n_c:] = rng.poisson(lam[:, 1], size=(n_sims, len(remaining)))
    home_m = np.zeros((len(all_m), n_t), dtype=np.int64)
    away_m = np.zeros_like(home_m)
    for j, r in enumerate(all_m):
        home_m[j, idx[r.home_team_id]] = 1
        away_m[j, idx[r.away_team_id]] = 1
    hp, ap = _points(gh, ga, rules)
    pts = hp @ home_m + ap @ away_m
    gf = gh @ home_m + ga @ away_m
    gag = ga @ home_m + gh @ away_m
    wins = (gh > ga).astype(np.int64) @ home_m + (ga > gh).astype(np.int64) @ away_m
    away_wins = (ga > gh).astype(np.int64) @ away_m
    away_gf = ga @ away_m
    opp_pts, opp_gd, opp_gf = pts @ opp, (gf - gag) @ opp, gf @ opp

    pos_counts = np.zeros((n_t, n_t), dtype=np.int64)
    round_counts = {r: np.zeros(n_t, dtype=np.int64) for r in ROUNDS}
    ko = _Knockout(model, rng)

    def no_h2h(group: Sequence[int]) -> list[Result]:
        return []  # the UCL league phase has no head-to-head criteria

    for s in range(n_sims):
        overall = {
            t: TeamTotals(
                points=int(pts[s, i]), goals_for=int(gf[s, i]), goals_against=int(gag[s, i]),
                wins=int(wins[s, i]), away_wins=int(away_wins[s, i]),
                away_goals_for=int(away_gf[s, i]), opp_points=int(opp_pts[s, i]),
                opp_goal_difference=int(opp_gd[s, i]), opp_goals_for=int(opp_gf[s, i]),
            )
            for i, t in enumerate(teams)
        }  # fmt: skip
        ranking = rank_from_totals(teams, overall, no_h2h, rules, rng)
        for p, t in enumerate(ranking):
            pos_counts[idx[t], p] += 1
        for rnd, clubs in ko.run(ranking).items():
            for t in clubs:
                round_counts[rnd][idx[t]] += 1

    probs = pos_counts / n_sims
    zone_probs = {
        z.key: {
            t: float(probs[i, z.first_position - 1 : z.last_position].sum())
            for i, t in enumerate(teams)
        }
        for z in rules.zones
    }
    matches = []
    for r in remaining:
        lh, la = model.expected_goals(r.home_team_id, r.away_team_id)
        ph, pd, pa = outcome_probabilities(model.score_matrix(r.home_team_id, r.away_team_id))
        matches.append(
            MatchForecast(r.fixture_id, r.home_team_id, r.away_team_id, ph, pd, pa, lh, la)
        )
    current = Counter[int]()
    played = Counter[int]()
    for r in completed:
        hg, ag = int(r.home_goals or 0), int(r.away_goals or 0)
        w, d, lo = rules.points_for_win, rules.points_for_draw, rules.points_for_loss
        current[r.home_team_id] += w if hg > ag else d if hg == ag else lo
        current[r.away_team_id] += w if ag > hg else d if hg == ag else lo
        played[r.home_team_id] += 1
        played[r.away_team_id] += 1
    return UCLForecast(
        competition="UCL",
        season_year=season_year,
        as_of=as_of,
        n_sims=n_sims,
        seed=seed,
        team_ids=teams,
        position_probs=probs,
        current_points={t: current[t] for t in teams},
        played={t: played[t] for t in teams},
        expected_points={t: float(pts[:, i].mean()) for i, t in enumerate(teams)},
        zone_probs=zone_probs,
        matches=matches,
        completed_matches=len(completed),
        notes=notes,
        round_probs={
            r: {t: float(c[idx[t]] / n_sims) for t in teams} for r, c in round_counts.items()
        },
    )


def round_sanity(forecast: UCLForecast) -> dict[str, float]:
    """Expected number of clubs in each round; must be 16, 8, 4, 2, 1."""
    return {r: sum(v.values()) for r, v in forecast.round_probs.items()}
