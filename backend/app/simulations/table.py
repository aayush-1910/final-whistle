"""
League table ordering with configurable tiebreakers.

Algorithm (applied to one set of final results):
  1. Group teams by the first criterion (points).
  2. Split each tied group by the next criterion, computed WITHIN that group
     (so head-to-head criteria use only matches between the tied clubs).
  3. Recurse into any sub-group that is still tied with the next criterion.
  4. Criteria we cannot compute (play-off, fair play, lots, coefficients)
     end the chain: the remaining tie is broken by a random draw.
  5. Play-off positions (e.g. Serie A 1st/17th): if the two clubs either side
     of that boundary are level on points, a 50/50 play-off decides it,
     overriding the tiebreakers.

Simplification (documented in docs/model-methodology.md): head-to-head
criteria are recomputed within each shrinking sub-group rather than
following each league's exact "restart" wording for 3+ club ties.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from app.domain.models import LeagueRules, Tiebreaker

# A result: (home_team, away_team, home_goals, away_goals)
Result = tuple[int, int, int, int]

_RANDOM = frozenset(
    {
        Tiebreaker.PLAYOFF,
        Tiebreaker.UNRESOLVED,
        Tiebreaker.DISCIPLINARY_POINTS,
        Tiebreaker.UEFA_COEFFICIENT,
    }
)


@dataclass
class TeamTotals:
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0
    wins: int = 0
    away_wins: int = 0
    away_goals_for: int = 0


def _totals(
    teams: Sequence[int], results: Sequence[Result], rules: LeagueRules
) -> dict[int, TeamTotals]:
    tot = {t: TeamTotals() for t in teams}
    w, d, lo = rules.points_for_win, rules.points_for_draw, rules.points_for_loss
    for h, a, hg, ag in results:
        if h not in tot or a not in tot:
            continue
        th, ta = tot[h], tot[a]
        th.goals_for += hg
        th.goals_against += ag
        ta.goals_for += ag
        ta.goals_against += hg
        ta.away_goals_for += ag
        if hg > ag:
            th.points += w
            th.wins += 1
            ta.points += lo
        elif hg < ag:
            ta.points += w
            ta.wins += 1
            ta.away_wins += 1
            th.points += lo
        else:
            th.points += d
            ta.points += d
    return tot


def _metric(crit: Tiebreaker) -> Callable[[TeamTotals], int] | None:
    return {
        Tiebreaker.POINTS: lambda t: t.points,
        Tiebreaker.GOAL_DIFFERENCE: lambda t: t.goals_for - t.goals_against,
        Tiebreaker.GOALS_FOR: lambda t: t.goals_for,
        Tiebreaker.WINS: lambda t: t.wins,
        Tiebreaker.AWAY_WINS: lambda t: t.away_wins,
        Tiebreaker.AWAY_GOALS_FOR: lambda t: t.away_goals_for,
    }.get(crit)


_H2H = {
    Tiebreaker.HEAD_TO_HEAD_POINTS: Tiebreaker.POINTS,
    Tiebreaker.HEAD_TO_HEAD_GOAL_DIFFERENCE: Tiebreaker.GOAL_DIFFERENCE,
    Tiebreaker.HEAD_TO_HEAD_GOALS_FOR: Tiebreaker.GOALS_FOR,
    Tiebreaker.HEAD_TO_HEAD_AWAY_GOALS_FOR: Tiebreaker.AWAY_GOALS_FOR,
}


def rank_teams(
    teams: Sequence[int],
    results: Sequence[Result],
    rules: LeagueRules,
    rng: np.random.Generator,
) -> list[int]:
    """Final order (1st first) for one set of results."""

    def among(group: Sequence[int]) -> list[Result]:
        members = set(group)
        return [r for r in results if r[0] in members and r[1] in members]

    return rank_from_totals(teams, _totals(teams, results, rules), among, rules, rng)


def rank_from_totals(
    teams: Sequence[int],
    overall: dict[int, TeamTotals],
    results_among: Callable[[Sequence[int]], Sequence[Result]],
    rules: LeagueRules,
    rng: np.random.Generator,
) -> list[int]:
    """Same as :func:`rank_teams`, but with precomputed totals (fast path for
    simulations).  ``results_among(group)`` returns matches between those clubs."""
    criteria = list(rules.tiebreakers)

    def order(group: list[int], idx: int) -> list[int]:
        if len(group) == 1:
            return group
        if idx >= len(criteria) or criteria[idx] in _RANDOM:
            shuffled = list(group)
            rng.shuffle(shuffled)
            return shuffled
        crit = criteria[idx]
        if crit in _H2H:
            mini = _totals(group, results_among(group), rules)
            fn = _metric(_H2H[crit])
            assert fn is not None
            key = {t: fn(mini[t]) for t in group}
        else:
            fn = _metric(crit)
            if fn is None:  # criterion we cannot compute (e.g. opponents' points)
                return order(group, len(criteria))
            key = {t: fn(overall[t]) for t in group}
        out: list[int] = []
        for value in sorted(set(key.values()), reverse=True):
            out.extend(order([t for t in group if key[t] == value], idx + 1))
        return out

    ranked = order(list(teams), 0)

    for pos in rules.playoff_positions:  # boundary between position pos and pos+1
        a, b = ranked[pos - 1], ranked[pos]
        if overall[a].points == overall[b].points and rng.random() < 0.5:
            ranked[pos - 1], ranked[pos] = b, a
    return ranked
