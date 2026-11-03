-- ============================================================================
-- 0004 — Champions League progression probabilities (Milestone 5)
--
-- For UCL runs, season_forecasts holds the league-phase position distribution
-- and round_probs holds the knockout progression:
--   {"round_of_16": p, "quarter_finals": p, "semi_finals": p, "final": p, "winner": p}
-- (probability of reaching / playing in each round; "winner" = lifting the trophy).
-- NULL for domestic leagues.
-- ============================================================================

alter table season_forecasts add column round_probs jsonb;
