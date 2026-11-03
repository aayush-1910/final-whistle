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

## 3. Monte Carlo simulation

Milestones 4 (domestic) and 5 (UCL).
