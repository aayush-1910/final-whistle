# Model Methodology

> Status: **baseline models implemented (Milestone 3), NOT yet validated.**
> All parameter values below are provisional defaults. They will be tuned and
> evaluated by time-ordered backtesting in Milestone 6. No forecast is published
> until then.

## Inputs

Models receive `MatchRecord`s (`backend/app/models/data.py`): kickoff time, competition, season,
teams, and the **90-minute score**. Extra time and shootouts are excluded because they would distort
goal rates. Awarded results are included with the awarded score. The 2024/25+ UCL final is
flagged `neutral` (no home advantage).

### Leakage rule

Every fit takes an explicit `as_of` time and learns only from matches that kicked off **strictly
before** it (`played_before`). Tests check that adding future matches changes nothing.

## 1. Elo ratings (`app/models/elo.py`)

Standard Elo on the 90-minute result, processed in kickoff order. The rating used for each match
is stored *before* that match updates it.

| Parameter | Default | Meaning |
|---|---|---|
| `base_rating` | 1500 | Starting rating |
| `k` | 20 | Update size |
| `home_advantage` | 65 | Rating points added to the home side |
| `use_margin` | true | K × 1 (0–1 goal margin), 1.5 (2), (11+n)/8 (n ≥ 3), per World Football Elo |
| `season_regression` | 0.20 | Fraction pulled back to 1500 at a team's first match of a new season |

**Initialisation (OD-002).** A club appearing for the first time in a domestic league whose
previous season is in the data (a promoted club) starts at the **mean rating of the clubs that
left that league** (the relegated clubs). Any other newcomer, including all clubs in the first
season of data and UCL-only clubs, starts at 1500. The first ~1,000 matches (most of 2023/24)
are burn-in: ratings there are still close to their starting values.

### Elo → home/draw/away (`app/models/elo_outcome.py`)

An ordered logistic model maps the pre-match rating difference *d* (incl. home advantage,
per 100 points) to outcomes: P(away) = σ(c1 − βd), P(away or draw) = σ(c2 − βd). β, c1 < c2
are fitted by maximum likelihood on matches before `as_of`, skipping the burn-in.

## 2. Poisson goal model (`app/models/poisson.py`)

```
log λ_home = μ + h·(not neutral) + attack[home] − defence[away]
log λ_away = μ                   + attack[away] − defence[home]
```

Goals are independent Poisson. Fitted by weighted maximum likelihood (L-BFGS-B, analytic
gradient checked against a numerical one in tests).

| Parameter | Default | Meaning |
|---|---|---|
| `decay_per_day` | 0.0019 | Match weight = exp(−ξ·days before `as_of`); half-life ≈ 1 year |
| `l2_penalty` | 2.0 | Shrinks every team toward average; also makes parameters identifiable |
| `max_goals` | 10 | Score grid 0–10 per side, renormalised (excluded mass is negligible) |

Outputs: expected goals, a full score-probability matrix, and home/draw/away probabilities.
The Dixon–Coles low-score correction is **not** used; it will only be added if backtesting shows
a benefit.

## Cross-competition strength (OD-004)

Both models use **one shared pool** across all five competitions. The UCL is the only link
between leagues: in our data, 152 UCL matches were between clubs from two of the four leagues.
League-strength differences are therefore learned from relatively few matches. This is a
known limitation, to be measured in Milestone 6.

38 of 143 clubs appear only in the UCL (median ~10 matches in the data). Elo starts them at
1500; Poisson shrinks them toward an average team. Neither has domestic results for them.

## Known limitations (to evaluate in Milestone 6)

1. **Promoted clubs in Poisson** start as an *average* team, which is likely too generous.
   Example: in the 2026-11-03 preview, Arsenal v Hull City was Elo 85% / Poisson 69% home win.
2. Thin cross-league link (see above).
3. Short history: data starts in 2023/24, so the first season is mostly burn-in.
4. No player, injury, or lineup information.
5. All parameters are untuned defaults.

## Sanity check (not a validation)

Fit on data before 2026-08-01, scored on the 425 matches of 2026/27 played by 2026-11-03:

| Model | Log loss | Brier |
|---|---|---|
| Base rates (always predict historical H/D/A frequencies) | 1.0524 | 0.6356 |
| Elo + ordered logit | 0.9563 | 0.5660 |
| Poisson | 0.9473 | 0.5591 |

This only shows the models are wired up correctly and carry signal. It is one small window
with untuned parameters, so **no accuracy claim is made**. Proper walk-forward backtesting,
calibration, and baseline comparison come in Milestone 6.

Reproduce: `backend/.venv/Scripts/python backend/scripts/preview_models.py`.

## 3. Domestic season simulation (`app/simulations/`)

1. Results that kicked off before `as_of` are fixed; every other fixture of the season is
   sampled from the Poisson model (independent home/away goal counts), 10,000 times by default.
2. Each simulated season is ranked with that league's **2026/27 tiebreakers**
   (`backend/rules/2026/*.json`), and finishing positions are counted.
3. Outputs per team: probability of each position, title probability, zone probabilities
   (Champions League places, relegation, etc.), expected points, expected position. Every
   remaining match also gets home/draw/away probabilities and expected goals.

### League rules (2026/27)

| League | Order after points | Special cases |
|---|---|---|
| EPL | GD, goals scored, head-to-head points, head-to-head away goals, play-off | |
| La Liga | **head-to-head points**, head-to-head GD, GD, goals scored, fair play (3+ clubs), play-off | |
| Bundesliga | GD, goals scored, head-to-head points, head-to-head away goals, away goals, play-off | 16th: relegation play-off (own zone, outcome not simulated) |
| Serie A | **head-to-head points**, head-to-head GD, GD, goals scored, lots | Ties for **1st or 17th** settled by a **play-off** |

**Source quality: secondary.** The rules were taken from the 2026/27 Wikipedia season pages,
which cite the official regulations (Premier League, RFEF Art. 29, DFL SpOL §II.2, Lega Serie A).
The official sites could not be read directly. Every rules file records `source_quality:
"secondary"`; publishing should require these to be checked against the primary documents.

Zones are **by league position only**. Domestic cup winners and any extra Champions League
place (from the UEFA association coefficient) can shift European places at season end. These
are not simulated.

### Approximations

- Criteria we have no data for (fair-play points, drawing of lots, neutral-venue play-offs other
  than Serie A's) are resolved by a seeded random draw.
- Serie A play-offs are modelled as 50/50 between the two clubs straddling 1st/2nd or 17th/18th.
  3+ club ties at those boundaries are approximated.
- Head-to-head criteria are recomputed within each shrinking tied sub-group; this may differ
  from a league's exact "restart" wording in rare 3+ club ties.
- **Team strength is fixed across simulations** (no parameter uncertainty), so outcomes far
  in the future probably look more certain than they are. Milestone 6 calibration will measure
  this. Adding strength uncertainty is the likely fix.

### Fixture-list check

Every ordered pair (home, away) must appear exactly once in a double round-robin. Duplicates
abort the run; missing pairs are simulated and reported in the run notes. This currently catches
La Liga's Rayo Vallecano v Athletic Club, which the provider lists as `CANCELLED`
(`docs/known-data-issues.md` #3).

### Reproducibility

Each run stores: model name/version, all parameters (incl. fitted μ and home advantage), the
rules used, data cutoff, seed, simulation count, and git commit (`model_runs` table). A fixed
seed reproduces a run exactly (tested). Runs are stored `is_published = false`.

Performance: about 1–2 s per league for 10,000 simulations.

## 4. Champions League simulation (`app/simulations/ucl.py`)

**Source: primary.** [Regulations of the UEFA Champions League 2026/27](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27-Online),
Arts. 17–22 (in force 29 July 2026), read directly on 2026-11-03. The Annex B bracket diagram is
published only as an image. Its paths were taken from UEFA's written draw explainers and
cross-checked against the actual 2024/25 draw.

| Stage | Rule implemented | Article |
|---|---|---|
| League phase | 36 clubs, 8 matches, one table; 1–8 → round of 16, 9–24 → play-offs, 25–36 out | 17.03–17.04 |
| Tiebreakers | GD, goals, away goals, wins, away wins, opponents' points, opponents' GD, opponents' goals, disciplinary points*, club coefficient* | 18.01 |
| Play-offs | 9/10 v 23/24, 11/12 v 21/22, 13/14 v 19/20, 15/16 v 17/18 (pairing drawn); seed hosts 2nd leg | 19.02 |
| Round of 16 | winners of the 15/16 ties meet 1/2, 13/14 → 3/4, 11/12 → 5/6, 9/10 → 7/8; each seeded pair split across the two halves by draw; seed hosts 2nd leg | 19.03, Annex B |
| QF / SF | per half: [1/2 slot v 7/8 slot], [3/4 slot v 5/6 slot], then their winners; the club that knocks out a seed takes its slot; 1–4 slot hosts QF 2nd leg, 1/2 slot hosts SF 2nd leg | 19.04 |
| Ties | aggregate goals, **no away-goals rule**, extra time at end of 2nd leg, then penalties | 20–21 |
| Final | single match at a neutral venue, extra time, penalties | 22 |

\* Not in our data: a tie reaching these is broken by a seeded random draw.

Approximations: extra-time goals use the match's expected goals × 30/90; penalty shoot-outs are 50/50.

**Validation of the league-phase table logic.** Rebuilding the 2025/26 league phase from match
results reproduces the official final ranking for all 36 clubs, with no random tiebreaks needed
(regression test `tests/integration/test_real_tables.py`).

**Every simulated bracket is audited** in tests: 2,000 simulated knockout phases are checked for
correct play-off pairings, round-of-16 opponents, slot inheritance, second-leg hosts, and that
clubs from the same seeded pair can only meet in the final. Expected clubs per round are exactly
16 / 8 / 4 / 2 / 1.

**Scope limit.** Supported only while no knockout fixtures exist in the data (today: league
phase, matchday 4). Once the play-off draw is made (late January 2027), the simulator must
condition on the real draw and on played knockout legs. **This must be built before then.**
Until it is, the simulator refuses to run instead of producing a wrong bracket.

## 5. Tiebreak engine validation on real tables

The same engine (`app/simulations/table.py`) reproduces the published final tables:

| Check | Result |
|---|---|
| EPL 2023/24, 2024/25, 2025/26 | all 20 positions match the provider's standings |
| Bundesliga 2023/24, 2024/25, 2025/26 | all 18 positions match |
| UCL league phase 2025/26 | all 36 positions match |
| La Liga 2024/25 (positions 7–18) | matches the published table, including a 3-club head-to-head mini-league (Getafe / Espanyol / Alavés) |
| Serie A 2023/24 (positions 8–18) | matches the published table (Torino above Napoli, Cagliari above Empoli on head-to-head) |

In head-to-head leagues, football-data.org's standings disagree with the official tables because
they order level clubs by goal difference (see `docs/known-data-issues.md` #5). Our engine follows
the official rules.
