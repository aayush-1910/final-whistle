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

Conditioning on reality (once the knockout phase has started)
  - Knockout fixtures from the provider fix the real pairings.  Legs played
    before ``as_of`` count with their real score (incl. extra time) and, for
    a level tie, the real shoot-out winner; unplayed legs are simulated.
  - Bracket decisions the provider does not publish until later rounds are
    read from an optional draw file, rules/<season>/UCL_draw.json (see
    ``load_draw``); without it those decisions are drawn at random, exactly
    as the regulations allow.
  - Any contradiction between data, draw file and regulations aborts the run.

Modelling approximations (documented in docs/model-methodology.md)
  - Extra-time goals: Poisson with the match's expected goals scaled by 30/90.
  - Penalty shoot-outs: 50/50.
  - Disciplinary points and club coefficient (last league-phase tiebreakers)
    are not in our data: a tie reaching them is broken by a seeded random draw.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.domain.models import Fixture, LeagueRules, Stage
from app.models.data import MatchRecord
from app.models.poisson import PoissonModel, outcome_probabilities
from app.simulations.domestic import MatchForecast, SeasonForecast, SimulationError, _points
from app.simulations.rules import RULES_DIR
from app.simulations.table import Result, TeamTotals, rank_from_totals

LEAGUE_PHASE_TEAMS = 36
MATCHES_PER_TEAM = 8
SEED_PAIRS: tuple[tuple[int, int], ...] = ((1, 2), (3, 4), (5, 6), (7, 8))
# (seeded positions, unseeded positions) for the knockout phase play-offs, and the
# round-of-16 seeded pair their winners meet (Art. 19.02-19.03, Annex B).
PLAYOFF_GROUPS: tuple[tuple[tuple[int, int], tuple[int, int], tuple[int, int]], ...] = (
    ((9, 10), (23, 24), (7, 8)),
    ((11, 12), (21, 22), (5, 6)),
    ((13, 14), (19, 20), (3, 4)),
    ((15, 16), (17, 18), (1, 2)),
)
ROUNDS = ("round_of_16", "quarter_finals", "semi_finals", "final", "winner")
KNOCKOUT_STAGES = {
    Stage.PLAYOFFS: "playoffs",
    Stage.LAST_16: "round_of_16",
    Stage.QUARTER_FINALS: "quarter_finals",
    Stage.SEMI_FINALS: "semi_finals",
    Stage.FINAL: "final",
}
TIES_PER_STAGE = {
    "playoffs": 8,
    "round_of_16": 8,
    "quarter_finals": 4,
    "semi_finals": 2,
    "final": 1,
}
EXTRA_TIME_FRACTION = 30 / 90


class UnsupportedStateError(SimulationError):
    pass


@dataclass
class UCLForecast(SeasonForecast):
    # Probability of reaching each round (playing in it); "winner" = winning the final.
    round_probs: dict[str, dict[int, float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Draw file
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class UCLDraw:
    """Bracket decisions from UEFA's draws, by league-phase POSITION (not club).

    ``r16_opponent``: seed position (1-8) -> seeded play-off position (9-16)
        whose tie's winner it meets in the round of 16.
    ``silver_half``: the four seed positions (one from each of 1/2, 3/4, 5/6,
        7/8) in the silver half of the bracket; the rest are in the blue half.
    Either may be omitted (that decision is then simulated as a random draw).
    """

    source: str
    r16_opponent: dict[int, int] | None = None
    silver_half: frozenset[int] | None = None

    def __post_init__(self) -> None:
        group_of = {s: r16 for seeded, _, r16 in PLAYOFF_GROUPS for s in seeded}
        if self.r16_opponent is not None:
            if sorted(self.r16_opponent) != list(range(1, 9)):
                raise SimulationError("Draw file: r16_opponent must cover seeds 1-8")
            if sorted(self.r16_opponent.values()) != list(range(9, 17)):
                raise SimulationError("Draw file: r16_opponent values must be 9-16, each once")
            for seed, po in self.r16_opponent.items():
                if seed not in group_of[po]:
                    raise SimulationError(
                        f"Draw file: seed {seed} cannot meet the winner of tie {po} (Art. 19.03)"
                    )
        if self.silver_half is not None and sorted(
            next(p for p in SEED_PAIRS if s in p) for s in self.silver_half
        ) != list(SEED_PAIRS):
            raise SimulationError("Draw file: silver_half needs exactly one seed from each pair")


def load_draw(season_year: int, base: Path = RULES_DIR) -> UCLDraw | None:
    path = base / str(season_year) / "UCL_draw.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    r16 = raw.get("r16_opponent")
    silver = raw.get("silver_half")
    return UCLDraw(
        source=raw.get("source", ""),
        r16_opponent=(
            {int(k): int(v) for k, v in r16.items() if not k.startswith("_")} if r16 else None
        ),
        silver_half=frozenset(int(s) for s in silver) if silver else None,
    )


# ---------------------------------------------------------------------------
# Knockout simulation
# ---------------------------------------------------------------------------
Known = dict[str, dict[frozenset[int], list[Fixture]]]


def _played(f: Fixture, as_of: datetime) -> bool:
    return f.is_completed and f.kickoff_utc is not None and f.kickoff_utc < as_of


class _Knockout:
    """Simulates the knockout phase for one league-phase ranking."""

    def __init__(
        self,
        model: PoissonModel,
        rng: np.random.Generator,
        trace: list[tuple[str, int, int, int]] | None = None,
        *,
        known: Known | None = None,
        as_of: datetime | None = None,
        draw: UCLDraw | None = None,
    ):
        self.model = model
        self.rng = rng
        self._lam: dict[tuple[int, int, bool], tuple[float, float]] = {}
        # When given, every tie is appended as (round, first-leg home, second-leg home,
        # winner); for the final, (round, club, club, winner).  Used by tests to audit
        # the bracket against the regulations.
        self.trace = trace
        self.known: Known = known or {}
        self.as_of = as_of
        self.draw = draw
        # Per-simulation strength shifts (team id -> (attack, defence)), see set_noise.
        self._noise: dict[int, tuple[float, float]] | None = None

    def set_noise(self, noise: dict[int, tuple[float, float]] | None) -> None:
        self._noise = noise

    def lam(self, home: int, away: int, neutral: bool = False) -> tuple[float, float]:
        key = (home, away, neutral)
        if key not in self._lam:
            self._lam[key] = self.model.expected_goals(
                home, away, neutral=neutral, competition="UCL"
            )
        lh, la = self._lam[key]
        if self._noise is not None:
            ah, dh = self._noise[home]
            aa, da = self._noise[away]
            lh, la = lh * float(np.exp(ah - da)), la * float(np.exp(aa - dh))
        return lh, la

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

    def _known_legs(self, rnd: str, a: int, b: int) -> list[Fixture] | None:
        ties = self.known.get(rnd)
        if not ties:
            return None
        legs = ties.get(frozenset((a, b)))
        if legs is None:
            raise UnsupportedStateError(
                f"{rnd}: the data has this round's ties, but not {a} v {b} as the bracket "
                "requires. The draw file or the data is inconsistent with the regulations."
            )
        return legs

    def _leg_goals(self, leg: Fixture) -> tuple[int, int]:
        assert self.as_of is not None
        if _played(leg, self.as_of):
            assert leg.home_score is not None and leg.away_score is not None
            return leg.home_score, leg.away_score
        return self._goals(leg.home_team_id, leg.away_team_id)

    def two_legs(self, rnd: str, first_leg_home: int, second_leg_home: int) -> int:
        legs = self._known_legs(rnd, first_leg_home, second_leg_home)
        if legs is not None:
            if len(legs) != 2:
                raise UnsupportedStateError(f"{rnd}: expected 2 legs, found {len(legs)}")
            leg1, leg2 = legs
            first_leg_home, second_leg_home = leg1.home_team_id, leg2.home_team_id
            a1, b1 = self._leg_goals(leg1)
            b2, a2 = self._leg_goals(leg2)
        else:
            leg2 = None
            a1, b1 = self._goals(first_leg_home, second_leg_home)
            b2, a2 = self._goals(second_leg_home, first_leg_home)
        agg_a, agg_b = a1 + a2, b1 + b2  # a = first-leg home club
        if agg_a != agg_b:
            winner = first_leg_home if agg_a > agg_b else second_leg_home
        elif leg2 is not None and self.as_of is not None and _played(leg2, self.as_of):
            # Real tie level after the second leg (incl. extra time): real shoot-out.
            sw = leg2.shootout_winner_team_id
            if sw is None:
                raise UnsupportedStateError(f"{rnd}: tie level on aggregate but no shoot-out data")
            winner = sw
        else:
            winner = self._after_draw(second_leg_home, first_leg_home, neutral=False)
        if self.trace is not None:
            self.trace.append((rnd, first_leg_home, second_leg_home, winner))
        return winner

    def final(self, a: int, b: int) -> int:
        legs = self._known_legs("final", a, b)
        if legs is not None and self.as_of is not None and _played(legs[0], self.as_of):
            f = legs[0]
            assert f.home_score is not None and f.away_score is not None
            if f.home_score != f.away_score:
                winner = f.home_team_id if f.home_score > f.away_score else f.away_team_id
            elif f.shootout_winner_team_id is not None:
                winner = f.shootout_winner_team_id
            else:
                raise UnsupportedStateError("final: level score but no shoot-out data")
        else:
            ga, gb = self._goals(a, b, neutral=True)
            winner = (a if ga > gb else b) if ga != gb else self._after_draw(a, b, neutral=True)
        if self.trace is not None:
            self.trace.append(("final", a, b, winner))
        return winner

    def _real_winner(self, rnd: str, a: int, b: int) -> int | None:
        """Winner of a tie that is complete in the data, else None."""
        legs = self.known.get(rnd, {}).get(frozenset((a, b)))
        if not legs or self.as_of is None or not all(_played(f, self.as_of) for f in legs):
            return None
        goals = {a: 0, b: 0}
        for f in legs:
            assert f.home_score is not None and f.away_score is not None
            goals[f.home_team_id] += f.home_score
            goals[f.away_team_id] += f.away_score
        if goals[a] != goals[b]:
            return a if goals[a] > goals[b] else b
        return legs[-1].shootout_winner_team_id

    def _consistent_halves(
        self, pos: dict[int, int], opponent_of_seed: dict[int, int]
    ) -> list[frozenset[int]]:
        """Silver-half seed sets consistent with the draw file and the published
        quarter-final / semi-final ties.  Raises if none is consistent."""
        options = [
            frozenset(choice)
            for choice in np.array(np.meshgrid(*SEED_PAIRS)).T.reshape(-1, 4).tolist()
        ]
        if self.draw is not None and self.draw.silver_half is not None:
            options = [o for o in options if o == self.draw.silver_half]
        qf, sf = self.known.get("quarter_finals"), self.known.get("semi_finals")
        if qf:
            holder = {}  # seed position -> club holding that slot after the round of 16
            for seed in range(1, 9):
                w = self._real_winner("round_of_16", pos[seed], opponent_of_seed[seed])
                if w is None:
                    raise UnsupportedStateError(
                        "Quarter-finals published before the round of 16 ended"
                    )
                holder[seed] = w
            seed_of = {c: s for s, c in holder.items()}
            pair_of = {s: p for p in SEED_PAIRS for s in p}
            for tie in qf:
                x, y = (seed_of.get(c) for c in tie)
                if (
                    x is None
                    or y is None
                    or {pair_of[x], pair_of[y]}
                    not in (
                        {(1, 2), (7, 8)},
                        {(3, 4), (5, 6)},
                    )
                ):
                    raise UnsupportedStateError("Quarter-final pairing contradicts Art. 19.04")
                options = [o for o in options if (x in o) == (y in o)]
            if sf:
                half_seed = {}  # quarter-final winner -> a seed position in its half
                for tie in qf:
                    a, b = tuple(tie)
                    w = self._real_winner("quarter_finals", a, b)
                    if w is None:
                        raise UnsupportedStateError("Semi-finals published before the QFs ended")
                    half_seed[w] = seed_of[a]
                for tie in sf:
                    x, y = (half_seed.get(c) for c in tie)
                    if x is None or y is None:
                        raise UnsupportedStateError("Semi-final club did not win a quarter-final")
                    options = [o for o in options if (x in o) == (y in o)]
        if not options:
            raise UnsupportedStateError(
                "No bracket is consistent with the draw file and the published ties"
            )
        return sorted(options, key=sorted)

    def _opponent_in(self, rnd: str, club: int) -> int | None:
        for pair in self.known.get(rnd, {}):
            if club in pair:
                (other,) = pair - {club}
                return other
        return None

    def run(self, ranking: Sequence[int]) -> dict[str, list[int]]:
        """``ranking[i]`` is the club in position i+1.  Returns clubs reaching each round."""
        pos = {p: ranking[p - 1] for p in range(1, LEAGUE_PHASE_TEAMS + 1)}
        rng = self.rng
        reached: dict[str, list[int]] = {r: [] for r in ROUNDS}

        # ---- Play-offs (Art. 19.02) -------------------------------------
        winner_of: dict[int, int] = {}  # seeded play-off position -> tie winner
        for seeded, unseeded, _ in PLAYOFF_GROUPS:
            if self.known.get("playoffs"):
                uns = []
                for s in seeded:
                    opp = self._opponent_in("playoffs", pos[s])
                    u = next((u for u in unseeded if pos[u] == opp), None)
                    if u is None:
                        raise UnsupportedStateError(
                            f"Play-off pairing for position {s} contradicts Art. 19.02"
                        )
                    uns.append(u)
            else:
                uns = list(unseeded)
                rng.shuffle(uns)
            for s, u in zip(seeded, uns, strict=True):
                winner_of[s] = self.two_legs("playoffs", pos[u], pos[s])

        # ---- Round-of-16 opponents (Art. 19.03) ---------------------------
        opponent_of_seed: dict[int, int] = {}
        for seeded, _, (s1, s2) in PLAYOFF_GROUPS:
            winners = {winner_of[p] for p in seeded}
            if self.known.get("round_of_16"):
                for s in (s1, s2):
                    opp = self._opponent_in("round_of_16", pos[s])
                    if opp not in winners:
                        raise UnsupportedStateError(
                            f"Round-of-16 opponent of position {s} is not a play-off winner "
                            "from the matching group (Art. 19.03)"
                        )
                    opponent_of_seed[s] = opp
            elif self.draw is not None and self.draw.r16_opponent is not None:
                for s in (s1, s2):
                    opponent_of_seed[s] = winner_of[self.draw.r16_opponent[s]]
            else:
                ws = [winner_of[p] for p in seeded]
                rng.shuffle(ws)  # which winner meets which seed is drawn
                opponent_of_seed[s1], opponent_of_seed[s2] = ws

        # ---- Halves (Art. 19.03-19.04) -------------------------------------
        constrained = (self.draw is not None and self.draw.silver_half is not None) or any(
            self.known.get(r) for r in ("quarter_finals", "semi_finals")
        )
        if constrained:
            options = self._consistent_halves(pos, opponent_of_seed)
            silver = options[int(rng.integers(len(options)))] if len(options) > 1 else options[0]
            halves = [
                {pair: next(s for s in pair if (s in silver) == (side == 0)) for pair in SEED_PAIRS}
                for side in (0, 1)
            ]
        else:
            halves = [{}, {}]
            for pair in SEED_PAIRS:
                seeds = list(pair)
                rng.shuffle(seeds)
                halves[0][pair], halves[1][pair] = seeds

        semi_finalists: list[int] = []
        for half in halves:
            slot: dict[tuple[int, int], int] = {}  # slot -> current holder
            for pair, seed in half.items():
                club, opp = pos[seed], opponent_of_seed[seed]
                reached["round_of_16"] += [club, opp]
                slot[pair] = self.two_legs("round_of_16", opp, club)  # seed hosts 2nd leg
            qf1 = slot[(1, 2)], slot[(7, 8)]
            qf2 = slot[(3, 4)], slot[(5, 6)]
            reached["quarter_finals"] += [*qf1, *qf2]
            w1 = self.two_legs("quarter_finals", qf1[1], qf1[0])  # 1/2 slot hosts 2nd leg
            w2 = self.two_legs("quarter_finals", qf2[1], qf2[0])  # 3/4 slot hosts 2nd leg
            reached["semi_finals"] += [w1, w2]
            semi_finalists.append(self.two_legs("semi_finals", w2, w1))  # 1/2 side hosts
        reached["final"] += semi_finalists
        reached["winner"].append(self.final(*semi_finalists))
        return reached


def _index_knockout(knockout: Sequence[Fixture], teams: set[int]) -> Known:
    known: Known = {}
    for f in knockout:
        rnd = KNOCKOUT_STAGES.get(f.stage)
        if rnd is None:
            continue
        if f.home_team_id not in teams or f.away_team_id not in teams:
            raise UnsupportedStateError(f"Knockout fixture {f.id} involves a non-UCL club")
        known.setdefault(rnd, {}).setdefault(
            frozenset((f.home_team_id, f.away_team_id)), []
        ).append(f)
    for rnd, ties in known.items():
        if len(ties) != TIES_PER_STAGE[rnd]:
            raise UnsupportedStateError(
                f"{rnd}: {len(ties)} of {TIES_PER_STAGE[rnd]} ties published; "
                "wait until the whole round is known"
            )
        for legs in ties.values():
            legs.sort(key=lambda f: (f.kickoff_utc or datetime.max, f.id or 0))
    return known


# ---------------------------------------------------------------------------
# Full competition
# ---------------------------------------------------------------------------
def simulate_ucl(
    records: Sequence[MatchRecord],
    season_year: int,
    model: PoissonModel,
    rules: LeagueRules,
    as_of: datetime,
    *,
    n_sims: int = 10_000,
    seed: int = 0,
    knockout: Sequence[Fixture] = (),
    draw: UCLDraw | None = None,
    strength_sd: float = 0.0,
) -> UCLForecast:
    """``knockout``: the season's knockout fixtures (domain Fixtures with full
    scores and shoot-outs), if any have been published.  ``draw``: bracket
    decisions from the draw file.  ``strength_sd``: per-simulation uncertainty
    in club strength (0 = fixed strengths)."""
    if model.as_of > as_of:
        raise SimulationError("Model was fitted with a later cutoff than as_of (leakage)")
    if (rules.competition_code, rules.season_start_year) != ("UCL", season_year):
        raise SimulationError("Rules do not match UCL / season")

    season = [
        r
        for r in records
        if r.competition == "UCL"
        and r.season_year == season_year
        and r.stage in (None, Stage.LEAGUE_STAGE.value)
    ]
    teams = sorted({t for r in season for t in (r.home_team_id, r.away_team_id)})
    games = Counter(t for r in season for t in (r.home_team_id, r.away_team_id))
    if (
        len(teams) != LEAGUE_PHASE_TEAMS
        or len(season) != LEAGUE_PHASE_TEAMS * MATCHES_PER_TEAM // 2
    ):
        raise UnsupportedStateError(
            f"UCL {season_year}: expected the 144 league-phase fixtures for 36 clubs, found "
            f"{len(season)} fixtures / {len(teams)} clubs"
        )
    if any(games[t] != MATCHES_PER_TEAM for t in teams):
        raise SimulationError("Each club must have exactly 8 league-phase fixtures")
    if len({frozenset((r.home_team_id, r.away_team_id)) for r in season}) != len(season):
        raise SimulationError("A pair of clubs meets twice in the league phase")

    idx = {t: i for i, t in enumerate(teams)}
    n_t = len(teams)
    completed = [r for r in season if r.is_played and r.kickoff_utc < as_of]
    remaining = [r for r in season if not (r.is_played and r.kickoff_utc < as_of)]
    known = _index_knockout(knockout, set(teams))
    if known and remaining:
        raise UnsupportedStateError(
            "Knockout fixtures exist but the league phase is not finished before as_of"
        )
    notes = []
    unknown = [t for t in teams if not model.knows(t)]
    if unknown:
        notes.append(f"{len(unknown)} club(s) have no model history: {unknown}")
    if known:
        notes.append(f"conditioned on published knockout rounds: {sorted(known)}")
    if draw is not None:
        notes.append(f"bracket draw file used: {draw.source or 'no source given'}")

    # Opponent matrix (each club's 8 opponents) for Art. 18.01 f-h.
    opp = np.zeros((n_t, n_t), dtype=np.int64)
    for r in season:
        opp[idx[r.home_team_id], idx[r.away_team_id]] += 1
        opp[idx[r.away_team_id], idx[r.home_team_id]] += 1

    # All league-phase matches as columns: completed are constant, remaining sampled.
    rng = np.random.default_rng(seed)
    z_att = z_def = None
    if strength_sd > 0:
        z_att = rng.normal(0.0, strength_sd, size=(n_sims, n_t))
        z_def = rng.normal(0.0, strength_sd, size=(n_sims, n_t))
    all_m = completed + remaining
    n_c = len(completed)
    lam = np.array(
        [model.expected_goals(r.home_team_id, r.away_team_id, competition="UCL") for r in remaining]
    ).reshape(-1, 2)
    gh = np.empty((n_sims, len(all_m)), dtype=np.int64)
    ga = np.empty_like(gh)
    gh[:, :n_c] = np.array([int(r.home_goals or 0) for r in completed], dtype=np.int64)
    ga[:, :n_c] = np.array([int(r.away_goals or 0) for r in completed], dtype=np.int64)
    if remaining:
        if z_att is not None and z_def is not None:
            hi = np.array([idx[r.home_team_id] for r in remaining])
            ai = np.array([idx[r.away_team_id] for r in remaining])
            gh[:, n_c:] = rng.poisson(lam[:, 0] * np.exp(z_att[:, hi] - z_def[:, ai]))
            ga[:, n_c:] = rng.poisson(lam[:, 1] * np.exp(z_att[:, ai] - z_def[:, hi]))
        else:
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
    ko = _Knockout(model, rng, known=known, as_of=as_of, draw=draw)

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
        if z_att is not None and z_def is not None:
            ko.set_noise({t: (float(z_att[s, i]), float(z_def[s, i])) for i, t in enumerate(teams)})
        for rnd, clubs in ko.run(ranking).items():
            for t in clubs:
                round_counts[rnd][idx[t]] += 1

    probs: NDArray[np.float64] = pos_counts / n_sims
    zone_probs = {
        z.key: {
            t: float(probs[i, z.first_position - 1 : z.last_position].sum())
            for i, t in enumerate(teams)
        }
        for z in rules.zones
    }
    matches = []
    for r in remaining:
        lh, la = model.expected_goals(r.home_team_id, r.away_team_id, competition="UCL")
        mat = model.score_matrix(r.home_team_id, r.away_team_id, competition="UCL")
        ph, pd, pa = outcome_probabilities(mat)
        matches.append(
            MatchForecast(r.fixture_id, r.home_team_id, r.away_team_id, ph, pd, pa, lh, la)
        )
    current = Counter[int]()
    played = Counter[int]()
    w, d, lo = rules.points_for_win, rules.points_for_draw, rules.points_for_loss
    for r in completed:
        hg, ag = int(r.home_goals or 0), int(r.away_goals or 0)
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
