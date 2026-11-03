# Milestone 0 — football-data.org Coverage Report

Generated: 2026-11-03T15:12:25.724267+00:00  
Target season: 2026 (2026/27)


## EPL (`PL`)

- **Name:** Premier League | type: LEAGUE
- **Current season:** 2026-08-21 → 2027-05-30, matchday 9
- **Seasons listed in metadata:** 128 (1888–2026) _(listed ≠ accessible)_
- **2026 teams:** 20
- **2026 matches:** 380 | statuses: {'FINISHED': 90, 'TIMED': 290}
- **Finished with full-time score:** 90/90
- **Stages:** {'REGULAR_SEASON': 380}
- **2026 standings:** 3 table(s), types ['AWAY', 'HOME', 'TOTAL']
- **2025 finished matches:** 380
- **2023 finished matches:** 380
- **2020 matches:** DENIED
- **2015 matches:** DENIED

## LA_LIGA (`PD`)

- **Name:** Primera Division | type: LEAGUE
- **Current season:** 2026-08-16 → 2027-05-30, matchday 11
- **Seasons listed in metadata:** 95 (1928–2026) _(listed ≠ accessible)_
- **2026 teams:** 20
- **2026 matches:** 380 | statuses: {'FINISHED': 109, 'TIMED': 20, 'SCHEDULED': 250, 'CANCELLED': 1}
- **Finished with full-time score:** 109/109
- **Stages:** {'REGULAR_SEASON': 380}
- **2026 standings:** 3 table(s), types ['AWAY', 'HOME', 'TOTAL']
- **2025 finished matches:** 380
- **2023 finished matches:** 380
- **2020 matches:** DENIED
- **2015 matches:** DENIED

## BUNDESLIGA (`BL1`)

- **Name:** Bundesliga | type: LEAGUE
- **Current season:** 2026-08-28 → 2027-05-22, matchday 8
- **Seasons listed in metadata:** 64 (1963–2026) _(listed ≠ accessible)_
- **2026 teams:** 18
- **2026 matches:** 306 | statuses: {'FINISHED': 72, 'TIMED': 36, 'SCHEDULED': 198}
- **Finished with full-time score:** 72/72
- **Stages:** {'REGULAR_SEASON': 306}
- **2026 standings:** 3 table(s), types ['AWAY', 'HOME', 'TOTAL']
- **2025 finished matches:** 306
- **2023 finished matches:** 306
- **2020 matches:** DENIED
- **2015 matches:** DENIED

## SERIE_A (`SA`)

- **Name:** Serie A | type: LEAGUE
- **Current season:** 2026-08-23 → 2027-05-30, matchday 10
- **Seasons listed in metadata:** 95 (1929–2026) _(listed ≠ accessible)_
- **2026 teams:** 20
- **2026 matches:** 380 | statuses: {'FINISHED': 100, 'TIMED': 90, 'SCHEDULED': 190}
- **Finished with full-time score:** 100/100
- **Stages:** {'REGULAR_SEASON': 380}
- **2026 standings:** 3 table(s), types ['AWAY', 'HOME', 'TOTAL']
- **2025 finished matches:** 380
- **2023 finished matches:** 380
- **2020 matches:** DENIED
- **2015 matches:** DENIED

## UCL (`CL`)

- **Name:** UEFA Champions League | type: CUP
- **Current season:** 2026-09-08 → 2027-01-27, matchday 4
- **Seasons listed in metadata:** 47 (1980–2026) _(listed ≠ accessible)_
- **2026 teams:** 36
- **2026 matches:** 144 | statuses: {'FINISHED': 54, 'TIMED': 90}
- **Finished with full-time score:** 54/54
- **Stages:** {'LEAGUE_STAGE': 144}
- **2026 standings:** 3 table(s), types ['AWAY', 'HOME', 'TOTAL']
- **2025 finished matches:** 189
- **2023 finished matches:** 125
- **2020 matches:** DENIED
- **2015 matches:** DENIED

## Summary

| Competition | 2026 teams | 2026 matches | Standings | Accessible history (probed [2025, 2023, 2020, 2015]) |
|---|---|---|---|---|
| EPL | 20 | 380 | ✅ | [2025, 2023] |
| LA_LIGA | 20 | 380 | ✅ | [2025, 2023] |
| BUNDESLIGA | 18 | 306 | ✅ | [2025, 2023] |
| SERIE_A | 20 | 380 | ✅ | [2025, 2023] |
| UCL | 36 | 144 | ✅ | [2025, 2023] |

## Errors

- `PL_2020_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `PL_2015_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `PD_2020_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `PD_2015_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `BL1_2020_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `BL1_2015_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `SA_2020_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `SA_2015_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `CL_2020_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.
- `CL_2015_matches`: HTTP 403 — The resource you are looking for is restricted and apparently not within your permissions. Please check your subscription.

**Requests made:** 40

## Follow-up: exact history boundary (2026-11-03, PL, 3 requests)

| Season | Result |
|---|---|
| 2024 | ✅ 380 finished matches |
| 2022 | ❌ HTTP 403 |
| 2021 | ❌ HTTP 403 |

**Free-tier accessible seasons: 2023, 2024, 2025 (complete) + 2026 (current).**
Assumed identical for all five competitions (2023/2025 confirmed for all; 2020/2015 denied for all).

## Findings

1. **2026/27 coverage is complete** for all five competitions: teams, the full fixture list,
   full-time scores on 100% of finished matches, and HOME/AWAY/TOTAL standings.
2. **Competition code `CL` confirmed** for the Champions League.
3. **History is 3 completed seasons.** Per domestic league, that is ~1,140 matches (Bundesliga ~918).
   Combined with API-Football Free (2022–2024), **2022 could be added**, giving 4 seasons, but that
   requires cross-provider team-ID mapping.
4. **UCL:** only the 144 `LEAGUE_STAGE` matches exist for 2026; the API's current-season end date is
   2027-01-27 (end of the league phase). Knockout fixtures are not published until the draws, so the
   simulator must generate the knockout bracket from the rules. Match counts confirm the formats:
   2025/26 = 189 (new format: 144 + 16 + 16 + 8 + 4 + 1); 2023/24 = 125 (old group format).
   **Only one completed season (2025/26) uses the current UCL format.**
5. Free tier allows 10 requests/minute; a full refresh of all five competitions is ~15 requests.
