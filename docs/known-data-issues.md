# Known Data Issues

Provider-data quirks found by the ingestion checks. Each is recorded here
instead of being silently "fixed" in code.

| # | Found | Competition / season | Issue | Handling |
|---|---|---|---|---|
| 1 | 2026-11-03 | Bundesliga 2024/25 | Union Berlin v Bochum (14 Dec 2024) was **awarded 2-0 to Bochum** after the goalkeeper was hit by an object from the crowd. football-data.org's match data has the award, but its **standings omit the match** (both teams show 33 played; Bochum 22 pts instead of 25). | Our rebuilt table includes the award. Ingestion run is marked `partial` with the discrepancy stored in `ingestion_runs.consistency`. Treat our match-based table as authoritative for this season. |
| 2 | 2026-11-03 | UCL 2024/25 | The final arrives with `matchday: 0`. | Normalizer maps matchday `0` to `NULL` (a single-match final has no matchday). |
| 3 | 2026-11-03 | La Liga 2026/27 | Rayo Vallecano v Athletic Club (matchday 8) has status `CANCELLED` but a future kickoff (2026-12-09). It is probably rescheduled, not truly cancelled. | **Handled (Milestone 4).** The simulator's fixture-list check finds the missing pair and simulates it, noting it in the run. This applies to any fixture missing from a double round-robin, whatever its provider status. |
| 4 | 2026-11-03 | All, shootout matches | `score.fullTime` **includes penalty-shootout goals** (e.g. a 1-1 won 4-3 on penalties shows `fullTime` 5-4). | Normalizer stores goals in play (regular + extra time) as the score, and the shootout separately. Verified: `fullTime = regularTime + extraTime + penalties` held for every such match. |
| 5 | 2026-11-03 | La Liga, Serie A (all seasons); UCL 2024/25 | **Provider standings ignore head-to-head tiebreakers**: level clubs are ordered by goal difference. Example: La Liga 2024/25, the provider shows Osasuna 8th and Rayo 9th, but Rayo finished 8th on head-to-head points (published table). Same for Real Sociedad/Valencia, Espanyol/Alavés, Girona/Sevilla (2024/25), Torino/Napoli and Cagliari/Empoli (Serie A 2023/24), and Real Madrid/Bayern (UCL 2024/25 league phase). | **Never use provider standings positions for ranking.** We compute tables ourselves with each competition's rules; the ingestion cross-check compares points/goals only, which are unaffected. Verified against published tables in `tests/integration/test_real_tables.py`. |
