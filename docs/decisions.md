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

## OD-002 — Promoted-team Elo initialization

**Status:** Open  
**Question:** How should newly promoted teams or clubs with no prior Elo
history be initialized?  
**Options:**
1. League-average starting rating.
2. Second-tier final rating with a decay factor.
3. Fixed starting value (e.g., 1300).

**Decision:** _pending_

---

## OD-003 — Forecast refresh cadence

**Status:** Open  
**Question:** Should V1 refresh forecasts automatically after every completed
match, on a scheduled basis (e.g., daily), or manually?  
**Decision:** _pending_

---

## OD-004 — Cross-league Elo for UCL

**Status:** Open  
**Question:** How should Elo ratings be shared or translated across domestic
leagues for UCL simulation?  
**Decision:** _pending_

