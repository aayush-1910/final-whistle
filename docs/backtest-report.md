# Backtest Report (Milestone 6)

> Generated 2026-11-03 16:55 UTC by `backend/scripts/backtest.py`.
> Walk-forward: models are refit every week using only matches that kicked off earlier,
> then predict that week. Outcome = result after 90 minutes. Lower is better for all scores
> except accuracy.

## Design

| Period | Dates | Use |
|---|---|---|
| Burn-in | 2023/24 | training data only, never scored |
| Tuning | 2024-07-01 → 2025-07-01 (1635 matches) | parameters chosen by log loss |
| **Test** | 2025-07-01 → 2026-11-03 (2060 matches) | chosen settings scored once |

## Chosen settings (from the tuning period only)

- **Poisson:** decay 0.0019/day, L2 4.0, group priors on (tuning log loss 0.9806; 50 configurations tried)
- **Elo:** K 30, home advantage 90, season regression 0.2 (tuning log loss 0.9860; 45 configurations tried)
- **Blend:** 0.3 × Elo + 0.7 × Poisson (tuning log loss 0.9790)

## Test-period results

| Model | Log loss | Brier | RPS | Accuracy | Calibration error (ECE) |
|---|---|---|---|---|---|
| Poisson (tuned) | 0.9812 | 0.5831 | 0.2016 | 53.5% | 0.0122 |
| Poisson (default) | 0.9815 | 0.5829 | 0.2016 | 53.7% | 0.0165 |
| Blend (tuned) | 0.9819 | 0.5838 | 0.2019 | 53.1% | 0.0106 |
| Elo (default) | 0.9908 | 0.5903 | 0.2046 | 51.7% | 0.0072 |
| Elo (tuned) | 0.9924 | 0.5914 | 0.2051 | 52.3% | 0.0090 |
| base rates | 1.0662 | 0.6447 | 0.2310 | 44.9% | 0.0092 |

### Is **Poisson (tuned)** really better? (paired bootstrap, test period)

Mean log-loss difference per match; negative = the best model is better. If the 95%
interval includes 0, the difference is not distinguishable from noise.

| Comparison | Mean difference | 95% interval |
|---|---|---|
| Poisson (tuned) vs base rates | -0.0850 | [-0.1008, -0.0694] ✓ |
| Poisson (tuned) vs Elo (default) | -0.0096 | [-0.0169, -0.0029] ✓ |
| Poisson (tuned) vs Poisson (default) | -0.0003 | [-0.0027, +0.0024] |
| Poisson (tuned) vs Elo (tuned) | -0.0112 | [-0.0184, -0.0042] ✓ |
| Poisson (tuned) vs Blend (tuned) | -0.0006 | [-0.0027, +0.0014] |

### Log loss by competition (test period)

| Competition | Matches | base rates | Elo (default) | Poisson (default) | Elo (tuned) | Poisson (tuned) | Blend (tuned) |
|---|---|---|---|---|---|---|---|
| EPL | 470 | 1.0829 | 1.0475 | 1.0287 | 1.0434 | 1.0315 | 1.0319 |
| LA_LIGA | 489 | 1.0561 | 0.9828 | 0.9734 | 0.9877 | 0.9714 | 0.9741 |
| BUNDESLIGA | 378 | 1.0667 | 0.9780 | 0.9813 | 0.9807 | 0.9797 | 0.9777 |
| SERIE_A | 480 | 1.0795 | 0.9710 | 0.9787 | 0.9736 | 0.9790 | 0.9754 |
| UCL | 243 | 1.0268 | 0.9569 | 0.9121 | 0.9582 | 0.9103 | 0.9198 |

### Calibration of Poisson (tuned) (test period)

All home/draw/away probabilities pooled. Well calibrated means 'Observed' ≈ 'Predicted'.

| Predicted range | Count | Predicted (mean) | Observed |
|---|---|---|---|
| 0%–10% | 102 | 7.6% | 4.9% |
| 10%–20% | 782 | 16.1% | 14.6% |
| 20%–30% | 2507 | 24.9% | 25.0% |
| 30%–40% | 1045 | 34.7% | 32.5% |
| 40%–50% | 775 | 44.8% | 45.3% |
| 50%–60% | 516 | 54.5% | 55.6% |
| 60%–70% | 290 | 64.4% | 71.0% |
| 70%–80% | 128 | 74.2% | 78.9% |
| 80%–90% | 33 | 83.8% | 87.9% |
| 90%–100% | 2 | 91.0% | 50.0% |

## Caveats

- One test window (~1.3 seasons). Results can shift with more data.
- Tuning used a single season; the grid is coarse.
- Match-level results say nothing yet about **season-level** calibration (title/relegation probabilities). That is evaluated separately.

## Season-level backtest (title / top 4 / relegation / final position)

> Generated 2026-11-03 16:56 UTC by `backend/scripts/season_backtest.py`.
> Forecasts made on 1 Oct, 15 Nov, 15 Jan and 15 Mar using only data before that date,
> 4000 simulations each, scored against the actual final tables (computed from the real
> results with each league's tiebreakers). Model: Poisson with the tuned settings.
> `strength_sd` adds uncertainty about how good each club really is.

### Tuning (2024/25): choosing `strength_sd`

| strength_sd | Position RPS | Champion Brier | Top-4 Brier | Relegation Brier | Sum of zone Briers |
|---|---|---|---|---|---|
| 0.00 | 0.07082 | 0.03317 | 0.04209 | 0.04992 | 0.12518 |
| 0.05 | 0.07056 | 0.03280 | 0.04235 | 0.04987 | 0.12502 |
| 0.10 | 0.07039 | 0.03199 | 0.04260 | 0.05029 | 0.12488 |
| 0.15 ← | 0.07012 | 0.03096 | 0.04335 | 0.05074 | 0.12505 |
| 0.20 | 0.07053 | 0.03050 | 0.04450 | 0.05217 | 0.12718 |
| 0.30 | 0.07214 | 0.02942 | 0.04837 | 0.05483 | 0.13262 |

### Test (2025/26)

| strength_sd | Position RPS | Champion Brier | Top-4 Brier | Relegation Brier | Sum of zone Briers |
|---|---|---|---|---|---|
| 0.00 | 0.07999 | 0.00747 | 0.06775 | 0.06148 | 0.13671 |
| 0.15 | 0.07885 | 0.00904 | 0.06608 | 0.06216 | 0.13728 |

### Reliability of zone probabilities, 2025/26, strength_sd = 0.00

Title, top-4 and relegation probabilities pooled (4 leagues × 4 dates).

| Predicted range | Count | Predicted (mean) | Observed |
|---|---|---|---|
| 0%–2% | 617 | 0.1% | 0.3% |
| 2%–10% | 104 | 5.2% | 8.7% |
| 10%–30% | 67 | 17.7% | 11.9% |
| 30%–50% | 37 | 40.0% | 48.6% |
| 50%–70% | 32 | 59.6% | 59.4% |
| 70%–90% | 29 | 79.7% | 69.0% |
| 90%–98% | 18 | 94.6% | 88.9% |
| 98%–100% | 32 | 99.6% | 100.0% |

### Reliability of zone probabilities, 2025/26, strength_sd = 0.15

Title, top-4 and relegation probabilities pooled (4 leagues × 4 dates).

| Predicted range | Count | Predicted (mean) | Observed |
|---|---|---|---|
| 0%–2% | 576 | 0.2% | 0.0% |
| 2%–10% | 123 | 5.4% | 8.1% |
| 10%–30% | 88 | 17.5% | 9.1% |
| 30%–50% | 42 | 39.4% | 52.4% |
| 50%–70% | 40 | 58.8% | 60.0% |
| 70%–90% | 26 | 79.9% | 80.8% |
| 90%–98% | 17 | 94.7% | 88.2% |
| 98%–100% | 24 | 99.5% | 100.0% |

Caveat: a season-level sample is small (each season gives 4 leagues × 4 dates, and outcomes
within a season are strongly correlated), so these numbers are indicative, not precise.
