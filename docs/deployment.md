# Deployment and operations

Three independent pieces. Each can be hosted separately, and none is live until the steps
below are done.

| Piece | What it does | Where (default plan) |
|---|---|---|
| **Data refresh** | Daily import, then forecast, then publish (`backend/scripts/refresh.py`) | GitHub Actions (`.github/workflows/refresh.yml`) |
| **API** | Read-only FastAPI (`backend/`, `backend/Dockerfile`) | Container host (see OD-006 in `decisions.md`) |
| **Dashboard** | Static React build (`frontend/`) | Vercel Hobby |

## Secrets: where each one goes

| Secret | Refresh (GitHub) | API host | Dashboard (Vercel) |
|---|---|---|---|
| `DATABASE_URL` (Supabase **Session pooler** string) | yes | yes | **never** |
| `FOOTBALL_DATA_ORG_KEY` | yes | no | **never** |
| `SUPABASE_SERVICE_ROLE_KEY`, `API_FOOTBALL_KEY` | no | no | **never** (unused) |

The dashboard gets no secrets at all. It only needs the public API address (`VITE_API_BASE`).
Anything in a `VITE_` variable is visible to every visitor.

**Why the pooler string:** Supabase's direct database host is IPv6-only on the free plan.
Your PC can reach it, but GitHub's runners and most container hosts can't. In Supabase,
go to **Connect → Session pooler** and copy the URI. It looks like
`postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.

## 1. Data refresh (GitHub Actions)

1. Push the repository to GitHub.
2. Go to **Settings → Secrets and variables → Actions → New repository secret** and add
   `DATABASE_URL` and `FOOTBALL_DATA_ORG_KEY`.
3. Go to **Actions → Data refresh → Run workflow** to test it once.
4. From then on it runs daily at 05:30 UTC. Each run's report is kept as an artifact for 30
   days. **If any step fails, the run fails and GitHub emails you.**

Notes:
- GitHub pauses scheduled workflows in repositories with no commits for 60 days. It emails a
  warning first; re-enable with one click in the Actions tab.
- The refresh never runs database migrations. Apply new migrations yourself
  (`scripts/migrate.py`), and do it before deploying code that needs them.

## 2. API

Build the container from `backend/` (`Dockerfile`). Set these environment variables on the host:

```
DATABASE_URL=<Session pooler string>
APP_ENV=production
LOG_FORMAT=json
CORS_ORIGINS=https://<your-dashboard>.vercel.app
```

Health checks: `GET /api/v1/health` (process up) and `GET /api/v1/health/ready` (database
answers). Point the host's health check at `/api/v1/health`. Health checks are never cached.
Data responses are cached for 60 s.

Logs: one JSON object per line. Requests slower than 3 s and server errors are logged at
WARNING level.

## 3. Dashboard (Vercel)

1. Import the GitHub repository in Vercel and set the **Root Directory** to `frontend`.
   Vercel detects Vite: build `npm run build`, output `dist`.
2. Add the environment variable `VITE_API_BASE=https://<your-api-host>` (no trailing slash).
3. Deploy, then put the Vercel address into the API's `CORS_ORIGINS`.

The app uses `#/...` routes, so no rewrite rules are needed.

## Monitoring checklist

| What | Where |
|---|---|
| Did today's refresh work? | GitHub Actions tab (and emails on failure); dashboard → **Data Centre** |
| Is the data stale? | The dashboard's sidebar status turns amber after 48 h without an import |
| Provider quota | Each refresh report lists the API requests used (about 15/day; free tier is 10/min) |
| Database size | Supabase dashboard (20 MB of 500 MB on 2026-11-04) |
| Hosting cost | Host dashboards. GitHub Actions and Vercel Hobby are free for this usage |

## Doing it by hand (local)

```
cd backend
.venv\Scripts\python scripts\refresh.py              # import, forecast, publish
.venv\Scripts\python scripts\refresh.py --no-import  # forecast/publish from stored data
```

Exit code 0 means everything was OK or skipped, 1 means a step failed (the summary says which
and why), and 2 means a setup problem (missing key or database settings).
