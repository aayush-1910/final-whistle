# Open Decisions

> Track unresolved design decisions here.  Each entry records the
> question, options considered, and the chosen rationale once decided.

---

## OD-001 — Football data provider(s)

**Status:** Decided 2026-11-03 — verified with a real key  
**Question:** Which provider(s) supply 2026/27 data and enough history for backtesting?

**Evidence (2026-11-03):**
- API-Football Free: **no 2026/27 access**; history limited to 2022–2024.
  Verified via real response — see `docs/milestone-0-coverage-report.md`.
- football-data.org Free tier: coverage page lists Premier League, La Liga, Bundesliga,
  Serie A and Champions League as "free. Forever." **Not yet verified with a real key**:
  current-season access, historical depth, rate limit, and terms of use.

**Options:**
1. **football-data.org Free as primary** for 2026/27 fixtures/results/standings, with
   API-Football Free (2022–2024) as a historical cross-check. Cost: ₹0. Needs a free account.
   Risk: historical depth for backtesting/Elo warm-up may be thin.
2. Option 1 **plus a historical results source** for Elo initialization and backtesting
   (e.g. football-data.co.uk CSVs for domestic leagues), subject to checking its terms.
   UCL history would remain a gap to fill separately.
3. **Paid API-Football tier** — single provider, full history. Recurring cost; README
   requires owner approval before any paid service.

**Decision:** Option 1 — football-data.org Free as primary provider. Adapter:
`backend/app/providers/football_data_org.py`. Coverage to be measured with
`backend/scripts/investigate_football_data_org.py`; Option 2 will be evaluated
if historical depth proves insufficient. No paid tier.

**Verified result:** all 5 competitions fully covered for 2026/27; free history = 2023–2025
(3 seasons). See `docs/milestone-0-football-data-org-report.md`. Thin history is a known
limitation for Elo warm-up and backtesting; adding more history (Option 2) is deferred
to Milestone 3 and is not a blocker.

---

## OD-002 — Initializing teams with no history

**Status:** Decided 2026-11-03 (provisional; to be evaluated in Milestone 6)  
**Question:** How should newly promoted teams or clubs with no prior history be initialized?  
**Options:**
1. League-average starting rating.
2. Second-tier final rating with a decay factor (needs second-tier data, which we don't have).
3. Fixed starting value (e.g., 1300).
4. Mean rating of the clubs relegated from that league the season before.

**Update (OD-005):** the Poisson model now learns a *promoted-club* mean (and a *UCL-only-club*
mean) and shrinks those clubs toward it (`group_priors`). Promoted clubs come out clearly weaker
than average (attack −0.32, defence −0.20 on the log scale, fit to 2025-07-01).

**Decision:** Elo uses option 4 for promoted clubs; a club starts at the mean rating of
the clubs it replaced, which is data-driven and needs no second-tier data. Clubs with no
earlier league season in the data, and UCL-only clubs, start at the base rating (1500).
The Poisson model currently shrinks all unknown clubs toward an *average* team, which is
probably too generous to promoted clubs. This is a known limitation to measure in Milestone 6.

---

## OD-003 — Forecast refresh cadence

**Status:** Decided 2026-11-04 (Milestone 8); the owner can change the schedule any time  
**Question:** Should V1 refresh forecasts automatically after every completed
match, on a scheduled basis (e.g., daily), or manually?  
**Decision:** **Daily, plus on demand.** `.github/workflows/refresh.yml` runs
`scripts/refresh.py` at 05:30 UTC (after the previous evening's matches) and can be started
by hand from the GitHub Actions tab. Each run imports the current season, re-forecasts only
competitions whose data changed (or whose forecast is over 7 days old), and publishes through
the quality gates. Rationale: probabilities only move when results come in; per-match refresh
would need a live-score feed and burn API quota for little gain; a daily job also keeps the
free Supabase project from pausing for inactivity. Cost: ~15 provider requests and ~1 minute
of compute per day.

---

## OD-004 — Cross-league strength for UCL

**Status:** Decided 2026-11-03 (provisional; to be evaluated in Milestone 6)  
**Question:** How should ratings be shared or translated across domestic leagues for UCL simulation?  
**Decision:** One shared rating pool (Elo) and one shared parameter set (Poisson) across all
five competitions. UCL matches are the only link between leagues: 152 matches in the data
were between clubs from two of the four leagues. 38 UCL-only clubs have no domestic data.
Per-league offsets or an external league-strength prior can be added if backtests show the
shared pool is miscalibrated across leagues.

---

## OD-005 — Production model choice and settings

**Status:** Decided 2026-11-03 from backtest evidence (`docs/backtest-report.md`, backtest runs #1–2)
**Question:** Which match model, with which settings, should drive forecasts?
**Protocol:** walk-forward with weekly refits; settings chosen on 2024/25 only; chosen settings
scored once on 2025/26 + 2026/27 to date (2,060 matches).
**Evidence:**
- Every model beats base rates by a wide margin (log loss 0.981 vs 1.066).
- **Poisson beats Elo** on the test period: −0.0096 log loss per match, 95% CI [−0.017, −0.003].
- **Tuning did not measurably help:** tuned vs default Poisson −0.0003, CI [−0.0027, +0.0024].
- **The Elo+Poisson blend** won during tuning but **did not beat Poisson alone** on test data
  (CI spans 0), so it is not used.
- Season level: per-simulation strength uncertainty (sd 0.15, chosen on 2024/25) was roughly
  neutral on 2025/26 overall (better final-position RPS and top-4 Brier, slightly worse
  title/relegation Brier), and reduced overconfidence in the 70–90% band.

**Decision:** `backend/app/models/config.py`, model version **0.2.0**:
Poisson (decay 0.0019/day, L2 4.0, group priors on), no blend, `strength_sd` 0.15 for domestic
leagues. The UCL simulator still uses fixed strengths; adding uncertainty there is a follow-up.
Re-run both backtests before changing any of these, and bump the model version.

**Update (v0.2.1, 2026-11-03):** `strength_sd` 0.15 also applied to the UCL simulator, for
consistency. It is not separately backtested (one season of the 36-club format).

---

## OD-006 — Hosting

**Status:** Decided 2026-11-04 by the owner: option 1 (Vercel + Render free + GitHub Actions)
**Measured needs (2026-11-04):** the refresh job takes ~30 s of compute for all five
competitions plus ~2 min of rate-limited imports, peak memory ~350 MB; the API is read-only,
answers in 0.1–2 s, and serves a personal dashboard (low traffic). Database: 20 MB of the
500 MB free Supabase allowance.
**Options:**
1. **Vercel (dashboard) + Render free web service (API) + GitHub Actions (refresh): ₹0.**
   Render's free service sleeps after ~15 min without visits; the first visit then takes
   ~30–60 s to wake.
2. **Vercel + Railway (API) + GitHub Actions: ~$5/month.** Always on, no wake-up delay.
3. **Fully static: ₹0, always fast.** The daily job writes every API response as JSON files
   and publishes them with the dashboard on Vercel; no API server at all. Needs extra work
   (exporting each fixture and team page), and the dashboard can only show what was exported.
**Decision:** Option 1, ₹0. Dashboard on Vercel Hobby; API on a Render free web service (Docker, Singapore region, next to the database; `render.yaml`); refresh on GitHub Actions. Accepted trade-off: a 30–60 s wake-up after idle periods. Moving to option 2 later only means changing the API host.
