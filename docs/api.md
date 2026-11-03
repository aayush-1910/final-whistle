# Final Whistle API (v1)

Read-only JSON API for the dashboard. Base path: `/api/v1`.
Interactive docs with every field described: **http://localhost:8000/docs** (while the backend runs).

## Ground rules for the dashboard

1. **Published vs preview.** Forecast endpoints return only *published* runs. Add
   `?preview=true` to get the latest unpublished run. Its `run.is_published` is then `false`,
   and the UI must label it as a preview. Runs are published with
   `backend/scripts/publish_run.py`, which checks model version, stored backtests, rules
   source quality and data freshness first.
2. **Always show provenance.** Every forecast carries a `run` block: `model_version`,
   `data_cutoff` (only matches before this were used), `run_at`, `simulation_count`,
   `rules_source_quality`. Show at least the data cutoff and model version next to any
   probability.
3. **Always show freshness.** Data responses carry `freshness`. `is_stale = true` means the last
   import is more than 48 h old; say so instead of hiding it.
4. **Probabilities are 0–1 floats** with full precision. Round for display (README: one decimal
   place of a percentage is usually enough).
5. **No write endpoints exist.** Imports, simulations and publishing run from scripts only.

## Endpoints

| Method & path | Purpose | Query params |
|---|---|---|
| `GET /health` | Process is up (no DB check) | |
| `GET /health/ready` | Database answers | |
| `GET /competitions` | All 5 competitions: current season, freshness, latest published run, whether a preview exists | |
| `GET /competitions/{code}/seasons/{year}/standings` | Current table computed from results (UCL: league phase) incl. last-5 form | |
| `GET /competitions/{code}/seasons/{year}/forecast` | Season forecast for every team: P(each position), zones, expected points/position; UCL also round-by-round | `preview` |
| `GET /fixtures/upcoming` | Fixtures in the next N days, with H/D/A + xG where a run covers them | `days` (1–60, default 7), `competition`, `preview` |
| `GET /fixtures/{id}` (alias `/fixtures/{id}/forecast`) | One fixture: result or forecast, top-10 likely scorelines, 6×6 score grid | `preview` |
| `GET /teams/{id}` | Team: seasons with position/points, last 5 results, next 5 fixtures | `preview` |
| `GET /teams/{id}/forecast-history` | A team's forecast run by run (for trend charts) | `competition`, `season` (required), `preview` |
| `GET /competitions/{code}/seasons/{year}/timeline` | Title probability (UCL: winning it) for every club, one point per matchday (latest run per matchday; 0 = pre-season) | `preview` |
| `GET /data/status` | Per competition: fixtures played/remaining, freshness, run counts; plus the latest import runs | `limit` (1–100, default 20) |
| `GET /models/versions` | Model versions with run counts; which is current | |
| `GET /models/performance` | Latest stored backtests (match level and season level) with all metrics | |
| `GET /forecasts/{run_id}` | A specific run (published or not; the run says which) | |

`code` is one of `EPL`, `LA_LIGA`, `BUNDESLIGA`, `SERIE_A`, `UCL` (uppercase). `year` is the
season's start year (`2026` = 2026/27).

Errors: `404` with a `detail` message (unknown competition/season/fixture/team, or no published
forecast yet); `422` for invalid parameters; `503` if the database is unreachable.

"Latest" run always means the latest **data cutoff**, not the latest execution: historical
backfill runs (`run.is_backfill = true`) are computed later but describe an earlier point in the
season. Team refs carry `crest_url` and competitions `emblem_url` (provider image URLs).

## Key response shapes (abridged)

**Season forecast** (`/competitions/EPL/seasons/2026/forecast?preview=true`)

```json
{
  "competition": "EPL", "season": 2026, "season_label": "2026/27",
  "run": {"run_id": 11, "model_version": "0.2.1", "data_cutoff": "2026-11-03T17:20:00Z",
          "simulation_count": 10000, "is_published": false, "rules_source_quality": "primary", "...": "..."},
  "freshness": {"last_ingested_at": "2026-11-03T15:51:52Z", "is_stale": false, "...": "..."},
  "zones": [{"key": "champion", "label": "Champions", "first_position": 1, "last_position": 1},
            {"key": "champions_league", "label": "Champions League", "first_position": 1, "last_position": 4},
            {"key": "relegation", "label": "Relegation", "first_position": 18, "last_position": 20}],
  "rounds": null,
  "teams": [{"team": {"id": 1, "name": "Arsenal FC", "short_name": "Arsenal", "tla": "ARS"},
             "current_points": 24, "played": 9, "expected_points": 84.9, "expected_position": 1.4,
             "position_probs": [0.724, 0.21, "... 20 values, index 0 = P(1st)"],
             "zone_probs": {"champion": 0.724, "champions_league": 0.987, "relegation": 0.0},
             "round_probs": null}],
  "disclaimer": "Probabilities from a statistical model, not certainties. ..."
}
```

- Teams are sorted by expected position (UCL: by probability of winning the competition).
- Zone keys differ per league (`conference_league`, `relegation_playoff`, ...). Use the
  `zones` array for labels and order rather than hard-coding them.
- UCL: `zones` are `round_of_16` (top 8), `knockout_playoffs` (9–24), `eliminated` (25–36), and
  `round_probs` has `round_of_16`, `quarter_finals`, `semi_finals`, `final`, `winner` (the
  probability of *reaching* each round; `winner` = lifting the trophy).

**Fixture** (`/fixtures/upcoming`, `/fixtures/{id}`): `home`/`away` team refs, `kickoff_utc`
(UTC; convert for display), `status`, `stage`, scores (`null` = not played; extra time
included, shoot-out in `home_penalties`/`away_penalties`), and `forecast`
(`p_home`, `p_draw`, `p_away`, `xg_home`, `xg_away`, plus run id, model version, cutoff,
`is_published`), which is `null` when no visible run covers the fixture.

## Matchday history (backfill)

```bash
cd backend
.venv/Scripts/python scripts/backfill_forecasts.py                        # list what is missing
.venv/Scripts/python scripts/backfill_forecasts.py --save --publish --accept-secondary-rules
```

Refits the model at the end of each completed matchday using only earlier results, simulates the
season and stores the run as a backfill. Idempotent. UCL: league phase only.

## Running

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000     # or double-click dev.cmd
```

The Vite dev server proxies `/api/*` to port 8000, so the frontend calls `/api/v1/...`
directly. Typical latency to Supabase from the dev machine is 0.1–0.8 s per request.
