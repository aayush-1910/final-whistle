# Architecture

See the main README for the high-level data flow and stack.

## Backend layout

| Package | Responsibility | Knows about |
|---|---|---|
| `app/domain` | Canonical, self-validating types (`Fixture`, `Team`, `LeagueRules`, …) | nothing else |
| `app/providers` | HTTP clients for data providers; rate limiting; provider status mapping | domain enums |
| `app/ingestion` | Provider JSON → domain objects (`normalize_fdo`), standings cross-check (`consistency`), orchestration (`service`) | domain, providers, database |
| `app/database` | Connection, migrations, repository (upserts/reads) | domain |

Provider-specific code stays in `providers/` and `ingestion/normalize_*`. Adding a provider means a new client and a new normalizer, with no domain or database changes.

## Ingestion flow (`app/ingestion/service.py`)

```text
football-data.org --3 requests--> raw JSON saved to backend/raw_responses/fdo/<date>/ (git-ignored)
                                      |
                                      v
                     normalize_fdo (bad records -> Issue, not a crash)
                                      |
                                      v
     ONE transaction: season -> teams -> season_teams -> fixtures (upsert) -> standings snapshot
                                      |
                                      v
         consistency: table rebuilt from fixtures vs provider standings
                                      |
                                      v
       ingestion_runs row: succeeded / partial / failed (+ issues, mismatches, error)
```

- **Idempotent.** Fixtures upsert on `(provider, provider_fixture_id)`, and a row is rewritten only if a value changed. Re-running reports `0 new, 0 updated`.
- **Atomic.** If anything fails, the data transaction rolls back and the run is still recorded as `failed` with the error.
- **Quota-safe.** 3 requests per competition-season; the client sleeps to stay under 10 requests/minute.

## Running

```bash
cd backend
.venv/Scripts/python scripts/migrate.py                 # create/upgrade tables
.venv/Scripts/python scripts/ingest.py                  # all 5 competitions, current season (15 requests)
.venv/Scripts/python scripts/ingest.py --all-seasons    # 2023-2026 (60 requests, ~6 min)
RUN_DB_TESTS=1 .venv/Scripts/python -m pytest tests/integration   # DB tests in a throwaway schema
```

## Database connection

`DATABASE_URL` if set, otherwise derived from `SUPABASE_URL` + `SUPABASE_DB_PASSWORD` (direct host `db.<ref>.supabase.co`, which is **IPv6-only** on the free plan). On a network without IPv6, set `DATABASE_URL` to the Session-pooler string from the Supabase dashboard.
