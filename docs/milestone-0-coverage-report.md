# Milestone 0 — API-Football Coverage Report

> ## ⚠ Correction (2026-11-03) — the zero counts below are plan restrictions, not missing data
>
> The original run did not record API `errors`. A follow-up probe
> (raw responses in `backend/raw_responses/`) shows:
>
> | Request | Result |
> |---|---|
> | `/teams?league=39&season=2026` | 0 results, error: **"Free plans do not have access to this season, try from 2022 to 2024."** |
> | `/teams?league=39&season=2024` | 20 results ✅ |
>
> **Conclusions:**
> - The Free plan **cannot access 2026/27 data** (teams, fixtures, standings) for any competition.
> - Free-plan history is limited to **2022–2024 (3 seasons)**. The "16 historical seasons" below come
>   from `/leagues` metadata, i.e. what exists on paid plans, not what this key can fetch.
> - API-Football Free is therefore **not viable as the primary V1 provider**. See `docs/decisions.md` OD-001.
>
> The script now records API errors in its report so this cannot recur silently.

---


Generated: 2026-11-03T15:03:02.034575+00:00
Target season: 2026 (2026/27)


## Account Status

- **Plan:** Free
- **Daily request limit:** 100
- **Requests used today (before this script):** ?


## English Premier League (EPL) — League ID 39

- **API name:** Premier League
- **Type:** League
- **Seasons available:** 17 (2010–2026)
- **2026/27 season present:** ✅ Yes
- **Teams (2026/27):** 0
- **Fixtures (2026/27):** 0
- **With scores:** 0
- **Statuses:** {}
- **Standings available:** ❌ No
- **Historical seasons (before 2026):** 16
- **Oldest historical:** 2010
- **Recent historical:** [2021, 2022, 2023, 2024, 2025]


## La Liga (LA_LIGA) — League ID 140

- **API name:** La Liga
- **Type:** League
- **Seasons available:** 17 (2010–2026)
- **2026/27 season present:** ✅ Yes
- **Teams (2026/27):** 0
- **Fixtures (2026/27):** 0
- **With scores:** 0
- **Statuses:** {}
- **Standings available:** ❌ No
- **Historical seasons (before 2026):** 16
- **Oldest historical:** 2010
- **Recent historical:** [2021, 2022, 2023, 2024, 2025]


## Bundesliga (BUNDESLIGA) — League ID 78

- **API name:** Bundesliga
- **Type:** League
- **Seasons available:** 17 (2010–2026)
- **2026/27 season present:** ✅ Yes
- **Teams (2026/27):** 0
- **Fixtures (2026/27):** 0
- **With scores:** 0
- **Statuses:** {}
- **Standings available:** ❌ No
- **Historical seasons (before 2026):** 16
- **Oldest historical:** 2010
- **Recent historical:** [2021, 2022, 2023, 2024, 2025]


## Serie A (SERIE_A) — League ID 135

- **API name:** Serie A
- **Type:** League
- **Seasons available:** 17 (2010–2026)
- **2026/27 season present:** ✅ Yes
- **Teams (2026/27):** 0
- **Fixtures (2026/27):** 0
- **With scores:** 0
- **Statuses:** {}
- **Standings available:** ❌ No
- **Historical seasons (before 2026):** 16
- **Oldest historical:** 2010
- **Recent historical:** [2021, 2022, 2023, 2024, 2025]


## UEFA Champions League (UCL) — League ID 2

- **API name:** UEFA Champions League
- **Type:** Cup
- **Seasons available:** 16 (2011–2026)
- **2026/27 season present:** ✅ Yes
- **Teams (2026/27):** 0
- **Fixtures (2026/27):** 0
- **With scores:** 0
- **Statuses:** {}
- **Standings available:** ❌ No
- **Historical seasons (before 2026):** 15
- **Oldest historical:** 2011
- **Recent historical:** [2021, 2022, 2023, 2024, 2025]


## Summary

| Competition | 2026/27 | Teams | Fixtures | Standings | Historical Seasons |
|---|---|---|---|---|---|
| EPL | ✅ | 0 | 0 | — | 16 |
| LA_LIGA | ✅ | 0 | 0 | — | 16 |
| BUNDESLIGA | ✅ | 0 | 0 | — | 16 |
| SERIE_A | ✅ | 0 | 0 | — | 16 |
| UCL | ✅ | 0 | 0 | — | 15 |

**Total API requests used by this script:** 21


## Quota Impact

This investigation used **21** of the daily 100-request budget.
Estimated remaining today: ~79
