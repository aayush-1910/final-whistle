"""
Monte Carlo simulation of the rest of a domestic league season.

1. Results that kicked off before ``as_of`` are fixed.
2. Every other fixture of the season is "remaining" and is sampled from the
   Poisson goal model (independent home/away goal counts).
3. Each simulated season is ranked with the league's real tiebreakers.
4. Finishing positions are counted across simulations.

Fixture-list check: a domestic league is a double round-robin, so every
ordered pair (home, away) must appear exactly once.  Duplicates are an error;
missing pairs (e.g. a fixture the provider marked cancelled that must still be
played) are simulated and reported in ``added_fixtures``.

Limitation: model parameters are fixed across simulations (no uncertainty in
team strength), which tends to make far-off outcomes look more certain than
they are.  To be measured by calibration in Milestone 6.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import permutations

import numpy as np
from numpy.typing import NDArray

from app.domain.models import LeagueRules
from app.models.data import MatchRecord
from app.models.poisson import PoissonModel, outcome_probabilities
from app.simulations.table import Result, TeamTotals, rank_from_totals

IntArray = NDArray[np.int64]


class SimulationError(ValueError):
    pass


@dataclass(frozen=True)
class MatchForecast:
    fixture_id: int | None  # None for a fixture added by the completeness check
    home_team_id: int
    away_team_id: int
    p_home: float
    p_draw: float
    p_away: float
    xg_home: float
    xg_away: float


@dataclass
class SeasonForecast:
    competition: str
    season_year: int
    as_of: datetime
    n_sims: int
    seed: int
    team_ids: list[int]
    position_probs: NDArray[np.float64]  # [team, position-1]
    current_points: dict[int, int]
    played: dict[int, int]
    expected_points: dict[int, float]
    zone_probs: dict[str, dict[int, float]]
    matches: list[MatchForecast]
    completed_matches: int
    added_fixtures: list[tuple[int, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def prob(self, team_id: int, position: int) -> float:
        return float(self.position_probs[self.team_ids.index(team_id), position - 1])

    @property
    def title_probs(self) -> dict[int, float]:
        return {t: float(self.position_probs[i, 0]) for i, t in enumerate(self.team_ids)}

    @property
    def expected_position(self) -> dict[int, float]:
        pos = np.arange(1, len(self.team_ids) + 1)
        return {t: float(self.position_probs[i] @ pos) for i, t in enumerate(self.team_ids)}


def _points(gh: IntArray, ga: IntArray, rules: LeagueRules) -> tuple[IntArray, IntArray]:
    home = np.where(
        gh > ga,
        rules.points_for_win,
        np.where(gh == ga, rules.points_for_draw, rules.points_for_loss),
    )
    away = np.where(
        ga > gh,
        rules.points_for_win,
        np.where(gh == ga, rules.points_for_draw, rules.points_for_loss),
    )
    return home, away


def simulate_league(
    records: Sequence[MatchRecord],
    competition: str,
    season_year: int,
    model: PoissonModel,
    rules: LeagueRules,
    as_of: datetime,
    *,
    n_sims: int = 10_000,
    seed: int = 0,
    strength_sd: float = 0.0,
) -> SeasonForecast:
    """``strength_sd`` > 0 draws, for each simulated season, a random shift of every
    club's attack and defence (normal, sd on the log-goals scale).  This represents
    uncertainty about how good the clubs really are, which fixed strengths ignore.
    0 reproduces the fixed-strength behaviour exactly."""
    if model.as_of > as_of:
        raise SimulationError("Model was fitted with a later cutoff than as_of (leakage)")
    if (rules.competition_code, rules.season_start_year) != (competition, season_year):
        raise SimulationError("Rules do not match the competition/season")

    season = [r for r in records if r.competition == competition and r.season_year == season_year]
    teams = sorted({t for r in season for t in (r.home_team_id, r.away_team_id)})
    if len(teams) != rules.team_count:
        raise SimulationError(
            f"{competition} {season_year}: {len(teams)} teams, rules say {rules.team_count}"
        )
    idx = {t: i for i, t in enumerate(teams)}
    n_t = len(teams)

    pair_count = Counter((r.home_team_id, r.away_team_id) for r in season)
    dupes = [p for p, c in pair_count.items() if c > 1]
    if dupes:
        raise SimulationError(f"Duplicate fixtures for pairs {dupes[:5]}")

    completed = [r for r in season if r.is_played and r.kickoff_utc < as_of]
    remaining: list[tuple[int | None, int, int, bool]] = [
        (r.fixture_id, r.home_team_id, r.away_team_id, r.neutral)
        for r in season
        if not (r.is_played and r.kickoff_utc < as_of)
    ]
    missing = [p for p in permutations(teams, 2) if p not in pair_count]
    remaining += [(None, h, a, False) for h, a in missing]
    notes: list[str] = []
    if missing:
        notes.append(
            f"{len(missing)} fixture(s) missing from the provider list were simulated: {missing}"
        )
    unknown = [t for t in teams if not model.knows(t)]
    if unknown:
        notes.append(
            f"{len(unknown)} team(s) have no model history and are treated as average: {unknown}"
        )

    # ---- fixed part: completed results ------------------------------------
    c_h = np.array([idx[r.home_team_id] for r in completed], dtype=np.int64)
    c_a = np.array([idx[r.away_team_id] for r in completed], dtype=np.int64)
    c_gh = np.array([r.home_goals for r in completed], dtype=np.int64)
    c_ga = np.array([r.away_goals for r in completed], dtype=np.int64)
    ch_pts, ca_pts = _points(c_gh, c_ga, rules)

    def base(values_home: IntArray, values_away: IntArray) -> IntArray:
        out = np.zeros(n_t, dtype=np.int64)
        np.add.at(out, c_h, values_home)
        np.add.at(out, c_a, values_away)
        return out

    zeros = np.zeros_like(c_gh)
    base_pts = base(ch_pts, ca_pts)
    base_gf = base(c_gh, c_ga)
    base_ga = base(c_ga, c_gh)
    base_w = base((c_gh > c_ga).astype(np.int64), (c_ga > c_gh).astype(np.int64))
    base_aw = base(zeros, (c_ga > c_gh).astype(np.int64))
    base_agf = base(zeros, c_ga)
    played = Counter[int]()
    for r in completed:
        played[r.home_team_id] += 1
        played[r.away_team_id] += 1
    completed_results: list[Result] = [
        (r.home_team_id, r.away_team_id, int(r.home_goals or 0), int(r.away_goals or 0))
        for r in completed
    ]

    # ---- sampled part: remaining fixtures ---------------------------------
    matches: list[MatchForecast] = []
    lam_h = np.empty(len(remaining))
    lam_a = np.empty(len(remaining))
    for j, (fid, h, a, neutral) in enumerate(remaining):
        lh, la = model.expected_goals(h, a, neutral=neutral, competition=competition)
        lam_h[j], lam_a[j] = lh, la
        mat = model.score_matrix(h, a, neutral=neutral, competition=competition)
        ph, pd, pa = outcome_probabilities(mat)
        matches.append(MatchForecast(fid, h, a, ph, pd, pa, lh, la))

    rng = np.random.default_rng(seed)
    r_n = len(remaining)
    if strength_sd > 0:
        z_att = rng.normal(0.0, strength_sd, size=(n_sims, n_t))
        z_def = rng.normal(0.0, strength_sd, size=(n_sims, n_t))
        hi = np.array([idx[h] for _, h, _, _ in remaining], dtype=np.int64)
        ai = np.array([idx[a] for _, _, a, _ in remaining], dtype=np.int64)
        lam_h_s = lam_h * np.exp(z_att[:, hi] - z_def[:, ai])
        lam_a_s = lam_a * np.exp(z_att[:, ai] - z_def[:, hi])
        gh = rng.poisson(lam_h_s).astype(np.int64)
        ga = rng.poisson(lam_a_s).astype(np.int64)
    else:
        gh = rng.poisson(lam_h, size=(n_sims, r_n)).astype(np.int64)
        ga = rng.poisson(lam_a, size=(n_sims, r_n)).astype(np.int64)
    home_m = np.zeros((r_n, n_t), dtype=np.int64)
    away_m = np.zeros((r_n, n_t), dtype=np.int64)
    for j, (_, h, a, _) in enumerate(remaining):
        home_m[j, idx[h]] = 1
        away_m[j, idx[a]] = 1
    hp, ap = _points(gh, ga, rules)
    pts = base_pts + hp @ home_m + ap @ away_m
    gf = base_gf + gh @ home_m + ga @ away_m
    gag = base_ga + ga @ home_m + gh @ away_m
    wins = base_w + (gh > ga).astype(np.int64) @ home_m + (ga > gh).astype(np.int64) @ away_m
    away_wins = base_aw + (ga > gh).astype(np.int64) @ away_m
    away_gf = base_agf + ga @ away_m

    rem_col = {(h, a): j for j, (_, h, a, _) in enumerate(remaining)}
    counts = np.zeros((n_t, n_t), dtype=np.int64)

    for s in range(n_sims):
        overall = {
            t: TeamTotals(
                points=int(pts[s, i]),
                goals_for=int(gf[s, i]),
                goals_against=int(gag[s, i]),
                wins=int(wins[s, i]),
                away_wins=int(away_wins[s, i]),
                away_goals_for=int(away_gf[s, i]),
            )
            for i, t in enumerate(teams)
        }

        def among(group: Sequence[int], s: int = s) -> list[Result]:
            members = set(group)
            out = [r for r in completed_results if r[0] in members and r[1] in members]
            for h, a in permutations(group, 2):
                j = rem_col.get((h, a))
                if j is not None:
                    out.append((h, a, int(gh[s, j]), int(ga[s, j])))
            return out

        order = rank_from_totals(teams, overall, among, rules, rng)
        for pos, t in enumerate(order):
            counts[idx[t], pos] += 1

    probs = counts / n_sims
    zone_probs = {
        z.key: {
            t: float(probs[i, z.first_position - 1 : z.last_position].sum())
            for i, t in enumerate(teams)
        }
        for z in rules.zones
    }
    return SeasonForecast(
        competition=competition,
        season_year=season_year,
        as_of=as_of,
        n_sims=n_sims,
        seed=seed,
        team_ids=teams,
        position_probs=probs,
        current_points={t: int(base_pts[i]) for i, t in enumerate(teams)},
        played={t: played[t] for t in teams},
        expected_points={t: float(pts[:, i].mean()) for i, t in enumerate(teams)},
        zone_probs=zone_probs,
        matches=matches,
        completed_matches=len(completed),
        added_fixtures=missing,
        notes=notes,
    )
