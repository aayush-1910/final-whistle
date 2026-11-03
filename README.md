# Final Whistle

> **Football analytics and season-forecasting platform** for the 2026/27 season.
>
> **Project status:** Planning / pre-development  
> **Initial release:** V1  
> **Primary purpose:** Generate transparent, data-driven predictions for the English Premier League, UEFA Champions League, La Liga, Bundesliga, and Serie A.

Final Whistle is a football forecasting application. It collects football data, calculates team-strength and goal-scoring estimates, simulates the remainder of competitions, and presents probabilities with clear explanations of when the data and forecast were last updated.

The first release is an **automated prediction engine only**. It is not a social prediction game, betting product, fantasy-football platform, or general-purpose football news site.

---

## 1. Product vision

Build a serious football analytics platform that answers questions such as:

- Which teams are most likely to win each domestic league?
- What is every club's probability of finishing in each league position?
- Which teams are most likely to qualify for continental competitions or be relegated, where those outcomes are configured for the relevant season?
- Which club is most likely to win the UEFA Champions League?
- What are the probabilities of a home win, draw, and away win for an upcoming match?
- How good have the forecasts been, and how well calibrated are their probabilities?

The application must communicate uncertainty honestly. A forecast is a probability distribution, not a guarantee or a statement that an outcome is certain.

### Product principles

1. **Evidence before presentation.** No percentage should be displayed unless it is generated from stored data and a reproducible model run.
2. **No fabricated data.** Missing or unsupported data must be shown as unavailable, not silently guessed.
3. **Time-aware predictions.** Every forecast must identify its generation time, data cutoff, model version, and simulation settings.
4. **No data leakage.** Historical backtests may only use information that would have been available at the simulated prediction date.
5. **Reproducibility.** A model run should be reproducible using its stored inputs, configuration, and random seed where applicable.
6. **Small, testable releases.** Build and validate the data pipeline and prediction engine before polishing the dashboard.
7. **Budget discipline.** Start with free tiers and local development. Do not buy a subscription until a real technical limitation requires it.

---

## 2. V1 scope

### Competitions in scope

| Competition | Competition type | V1 forecast outputs |
|---|---|---|
| English Premier League (EPL) | Domestic league | Title probability, expected position, position probabilities, top-four/top-five probability when the season's qualification rules are configured, relegation probability, match probabilities |
| La Liga | Domestic league | Title probability, expected position, position probabilities, configured European-qualification probability, relegation probability, match probabilities |
| Bundesliga | Domestic league | Title probability, expected position, position probabilities, configured European-qualification probability, relegation probability, match probabilities |
| Serie A | Domestic league | Title probability, expected position, position probabilities, configured European-qualification probability, relegation probability, match probabilities |
| UEFA Champions League (UCL) | League phase followed by knockout rounds | League-phase position probabilities, qualification probabilities, knockout progression probabilities, winner probability, match probabilities |

Competition rules and qualifying places can change by season. Store these as season-specific configuration rather than hardcoding assumptions into the model.

### V1 features

- Competition overview for all five competitions.
- Current competition table or league-phase table, with the source and update time visible.
- Title-winner probabilities for each domestic league.
- Predicted final table and probability of each finishing position for domestic leagues.
- Configurable top-four/top-five or other qualification probabilities, based on the competition's actual rules for 2026/27.
- Relegation probabilities for domestic leagues.
- Upcoming match probabilities: home win, draw, away win, plus expected goals and likely score distribution where supported by the model.
- Champions League league-phase and knockout simulation, following the 2026/27 format and draw/advancement rules.
- UCL winner probabilities and round-by-round progression probabilities.
- Forecast history and model-run metadata.
- Model evaluation page with historical backtesting and calibration metrics.
- Clear data freshness indicators and error/coverage states.

### Explicitly out of scope for V1

- User accounts, profiles, friend groups, private rooms, or leaderboards.
- User-submitted predictions or prediction contests.
- Betting, wagering, bookmaker integrations, odds comparison, or payment processing.
- Fantasy football, player transfers, squad builders, or fantasy points.
- News aggregation, social feeds, comments, chat, or notifications.
- AI chatbot or generative-AI features that do not improve forecasting.
- Mobile apps. V1 is a responsive web application.
- Deep player-level injury, lineup, or tracking-data models unless a reliable data source is later selected and validated.

These are not forgotten features; they are deliberately excluded to keep V1 focused and finishable.

---

## 3. Users and primary workflow

V1 is primarily for a football fan who wants to inspect an automated forecast rather than submit personal picks.

Typical workflow:

1. Open the Final Whistle overview.
2. Select a competition.
3. Inspect current standings or league-phase position.
4. Review title, qualification, relegation, and position probabilities.
5. Open a team or fixture to inspect its forecast and supporting factors.
6. Check when the data was refreshed and which model version generated the forecast.
7. Inspect historical model performance to understand whether the probabilities have been reliable.

---

## 4. Technical architecture

### Proposed stack

| Layer | Technology | Responsibility |
|---|---|---|
| Frontend | React + Vite | Responsive analytics dashboard |
| UI styling | Tailwind CSS | Consistent layout, typography, and styling |
| Charts | Recharts | Probability bars, position distributions, tables, and trends |
| Backend API | Python + FastAPI | Validated API endpoints and orchestration |
| Prediction engine | Python, NumPy, SciPy | Elo, Poisson, probability calculations, and simulation |
| Data processing | Pandas | Cleaning, normalization, and historical analysis |
| Database | Supabase PostgreSQL | Teams, competitions, fixtures, results, model runs, and forecasts |
| Data provider candidate | API-Football / API-Sports | Fixtures, results, standings, teams, and other covered football data |
| Source control | Git + GitHub | Version history, branches, and recovery points |
| Frontend hosting | Vercel Hobby initially | Static/frontend deployment for personal use |
| Backend hosting | Railway or another Python host, later | FastAPI deployment once local development is stable |
| Coding assistant | OpenAI Codex or another IDE agent | Assisted implementation and debugging; human review remains required |

The stack is a proposal for V1, not a reason to force every service into the first prototype. The engine should run locally first. Database and deployment integration can follow once the data model and engine are tested.

### High-level data flow

```text
Football data provider
        |
        v
Data ingestion and validation
        |
        v
Normalization and canonical IDs
        |
        v
PostgreSQL database
        |
        v
Feature generation
        |
        v
Elo + Poisson match model
        |
        v
Domestic league / UCL simulators
        |
        v
Forecast storage and model evaluation
        |
        v
FastAPI endpoints
        |
        v
React analytics dashboard
```

### Proposed repository layout

```text
final-whistle/
|
|-- README.md
|-- .gitignore
|-- .env.example
|-- docs/
|   |-- product-spec.md
|   |-- data-dictionary.md
|   |-- model-methodology.md
|   |-- architecture.md
|   `-- decisions.md
|
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- api/
|   |   |   `-- routes/
|   |   |-- core/
|   |   |   `-- config.py
|   |   |-- providers/
|   |   |   `-- api_football.py
|   |   |-- ingestion/
|   |   |-- database/
|   |   |-- domain/
|   |   |-- features/
|   |   |-- models/
|   |   |   |-- elo.py
|   |   |   |-- poisson.py
|   |   |   `-- calibration.py
|   |   |-- simulations/
|   |   |   |-- domestic.py
|   |   |   `-- ucl.py
|   |   `-- services/
|   |-- scripts/
|   |-- tests/
|   |-- requirements.txt
|   `-- .env
|
`-- frontend/
    |-- public/
    |-- src/
    |   |-- components/
    |   |-- pages/
    |   |-- features/
    |   |-- services/
    |   |-- hooks/
    |   `-- styles/
    |-- package.json
    `-- .env.local
```

The exact folders can be adjusted when implementation starts. Keep the provider, forecasting logic, API, and frontend separate so changing one layer does not require rewriting everything else.

---

## 5. Football data strategy

### Initial provider candidate: API-Football

API-Football is the first provider to test because it advertises endpoints for leagues, seasons, standings, teams, fixtures, results, statistics, and predictions across many competitions.

Official links:

- Website and plan information: <https://www.api-football.com/>
- API documentation: <https://www.api-football.com/documentation-v3>
- Pricing: <https://www.api-football.com/pricing>

The provider's public pricing page currently advertises a free tier with 100 requests per day. Access to historical seasons is limited by plan. These limits and entitlements can change; check the live account dashboard and current terms before relying on them.

**Provider status: provisional.** Do not assume the free plan contains every historical season required for reliable backtesting. Before committing, verify all five competitions, 2026 season coverage, fixture/result coverage, historical seasons, and the fields needed by the model.

### Data coverage checklist

For each competition, verify:

- The correct competition identity and season are returned.
- All participating teams are present and consistently identified.
- Current-season fixtures are available, including kickoff timestamps and status.
- Completed fixtures have valid home and away scores.
- Postponed, abandoned, cancelled, and awarded fixtures are represented distinctly.
- Standings or league-phase standings are available and agree with a trusted source.
- Historical seasons are available far enough back for model initialization and backtesting.
- Home/away team identities and competition-season identifiers remain stable.
- Rate limits, request costs, update frequency, and API terms are understood.

Do not begin a paid subscription until the coverage test demonstrates that the required information is unavailable on the free plan and the cost is justified.

### Backup provider to evaluate

Football-data.org is a possible fallback for fixtures, results, and tables:

- <https://www.football-data.org/>
- <https://www.football-data.org/documentation/quickstart>

Its free offering and historical coverage may differ from the requirements of this project. Evaluate it independently; do not assume it can replace every API-Football endpoint.

### Data-source rules

- Use documented APIs and respect provider terms, quotas, attribution rules, and licensing.
- Do not scrape websites or datasets whose terms prohibit the intended use.
- Do not assume that a publicly viewable page grants permission to collect or republish its data.
- Store the provider, source ID, retrieval time, and season for imported records.
- Keep the provider integration behind an adapter so another provider can be added later.
- Cache responses and avoid repeatedly requesting unchanged data.
- Never expose the API key in frontend code, public repositories, screenshots, or client-side network calls.

### Initial API request budget

The free API-Football tier is advertised at 100 requests/day. This is a strict prototype constraint, not a target to consume. The ingestion design should:

1. Fetch competition/season metadata sparingly.
2. Fetch fixtures and results in batches where supported.
3. Persist raw provider responses for diagnosis where permitted.
4. Normalize and upsert data instead of inserting duplicates.
5. Refresh only records that need updating.
6. Record quota usage and API errors.
7. Use exponential backoff for transient failures and stop retrying on quota exhaustion.

A daily refresh schedule is not required during the first local prototype. Manual refresh is acceptable while building and testing.

---

## 6. Data model and database planning

The database must distinguish source data from model outputs. Forecasts should never overwrite the raw results from the provider.

### Main entities

| Entity | Purpose | Important fields (conceptual) |
|---|---|---|
| `competitions` | Competition identity | `id`, `provider`, `provider_competition_id`, `name`, `code`, `format` |
| `seasons` | One competition season | `id`, `competition_id`, `season_label`, `start_date`, `end_date`, `rules_config` |
| `teams` | Canonical club identities | `id`, `name`, `short_name`, `country`, `provider_team_id` mapping |
| `team_provider_ids` | Map one canonical team to provider IDs | `team_id`, `provider`, `provider_team_id` |
| `fixtures` | Scheduled and completed matches | `id`, `season_id`, `home_team_id`, `away_team_id`, `kickoff_utc`, `status`, scores, provider ID |
| `team_match_features` | Features calculated for a team before a match | `fixture_id`, `team_id`, `as_of`, Elo rating, form, attack/defence estimates |
| `model_versions` | Identifies a model/configuration | `id`, `name`, `version`, `parameters`, `created_at` |
| `model_runs` | A specific forecast run | `id`, `model_version_id`, `season_id`, `data_cutoff`, `run_at`, `seed`, `simulation_count`, status |
| `match_forecasts` | Match outcome probabilities | `model_run_id`, `fixture_id`, home/draw/away probabilities, expected goals |
| `season_forecasts` | Season-level distributions | `model_run_id`, `team_id`, title probability, expected position, position probabilities, qualification/relegation probabilities |
| `ucl_round_forecasts` | UCL advancement probabilities | `model_run_id`, `team_id`, round, advancement probability, winner probability |
| `ingestion_runs` | Data-import audit trail | `provider`, `competition_id`, `season_id`, started/finished timestamps, request count, status, error |
| `backtest_runs` | Historical evaluation | `model_version_id`, evaluation window, metrics, cutoff rules, result summary |

This is a conceptual schema. Final column types, indexes, unique constraints, foreign keys, and migrations must be designed before creating production tables.

### Data integrity requirements

- Use canonical internal IDs; do not use club names as primary keys.
- Keep provider IDs in mapping fields/tables because IDs can differ between providers.
- Store kickoff times in UTC and convert them for display.
- Store timestamps for data retrieval and forecast generation.
- Use unique constraints to prevent duplicate fixtures and duplicate forecasts for the same model run.
- Preserve original provider statuses and map them to normalized statuses.
- Validate that a fixture does not have impossible scores or the same team as both home and away.
- Distinguish missing score from a score of zero.
- Version competition rules by season, especially UCL format and domestic qualification/relegation rules.
- Make migrations repeatable and keep them in source control.

---

## 7. Prediction methodology

V1 should begin with transparent statistical models rather than a large neural network. A simple, validated baseline is more useful than a complex model that cannot be evaluated.

### 7.1 Elo team-strength model

Elo estimates relative team strength from past results.

Inputs may include:

- Previous team ratings.
- Match result.
- Home advantage.
- Goal difference adjustment, if validation supports it.
- A rating update factor (`K`) selected through historical testing.

Key requirements:

- Ratings must be calculated chronologically.
- The rating used for a match must be the rating known before that match.
- Newly promoted or newly observed teams need a documented initialization method.
- Cross-competition club ratings need a carefully documented policy if UCL teams come from different domestic leagues.
- All parameters must be stored with the model version.

### 7.2 Poisson goal model

A Poisson model estimates the number of goals each team may score.

The model should estimate expected home and away goals using team attack strength, opponent defensive strength, and home advantage. The resulting goal distributions can be combined into probabilities for:

- Home win.
- Draw.
- Away win.
- Exact scorelines (within the supported goal range).
- Expected goals for each team.

Initial versions may use independent Poisson goal counts. More advanced variants, such as Dixon-Coles adjustments for low-score correlation, should only be introduced if backtesting shows a benefit.

### 7.3 Combining models

Elo and Poisson provide different information. V1 can compare them independently first, then test a transparent blend. Do not choose blending weights based on how well they fit the current season. Select parameters using historical, time-ordered validation.

### 7.4 Monte Carlo simulation

Monte Carlo simulation repeatedly samples possible outcomes for every remaining fixture and calculates the final competition state.

Initial target: **10,000 simulations per forecast run**, subject to runtime and convergence testing. This is a configurable starting point, not a guarantee that the estimates are precise.

For domestic leagues:

1. Start from the current validated table.
2. Keep already-completed results fixed.
3. Generate possible outcomes for every remaining fixture.
4. Update points, goals for, goals against, and goal difference.
5. Apply the competition's actual tiebreaking rules.
6. Record each team's finishing position for the simulation.
7. Repeat and aggregate the results.

Outputs include title probability, expected finishing position, probability of each finishing position, configured qualification probability, and relegation probability.

Do not label a probability as accurate merely because the simulation count is large. Simulation reduces Monte Carlo sampling noise; it does not fix bad data or a bad model.

### 7.5 Champions League simulation

The 2026/27 Champions League is not a standard domestic league. The simulator must reflect the competition's actual season format.

For the 36-team league phase, the current format has:

- Eight league-phase matches per team.
- Positions 1–8 advance directly to the Round of 16.
- Positions 9–24 enter the knockout play-offs.
- Positions 25–36 are eliminated.

The UCL simulator must account for the official 2026/27 competition rules, fixtures, tiebreakers, play-off path, draw constraints, two-legged ties, and final. Verify the rules from UEFA's official competition regulations before implementing the bracket. Do not rely on a simplified bracket if it changes the possible paths.

Official competition reference: <https://www.uefa.com/uefachampionsleague/>

### 7.6 Calibration and uncertainty

Probabilities must be evaluated for calibration. For example, events assigned a 30% probability should occur around 30% of the time across a sufficiently large set of comparable forecasts.

Display:

- Forecast probabilities.
- Forecast timestamp and data cutoff.
- Model name/version.
- Number of simulations.
- A concise uncertainty or methodology note.
- Data freshness status.

Avoid false precision. Rounding to one decimal place is usually enough for dashboard display; retain full precision internally.

---

## 8. Backtesting and model evaluation

Backtesting is mandatory before treating the forecasts as meaningful.

### Preventing data leakage

For every historical forecast date:

- Only use matches completed before that date/time.
- Do not use final standings, future match statistics, future team ratings, or future information.
- Calculate form and ratings as they would have existed at the time.
- Preserve historical fixture changes and match status where data permits.
- Split training and evaluation chronologically, not randomly.

### Metrics

Use more than raw winner accuracy.

| Metric | What it measures |
|---|---|
| Log loss | Penalizes confident, incorrect probabilities |
| Brier score | Measures squared error of probabilistic forecasts |
| Calibration / reliability curve | Checks whether predicted probabilities match observed frequencies |
| Accuracy | Simple proportion of correct categorical outcomes; useful but incomplete |
| Rank correlation / position error | Compares predicted league positions with final positions |
| Simulation stability | Checks whether results change materially when simulation count or seed changes |

Compare the model against simple baselines such as:

- Equal or historical base-rate probabilities where appropriate.
- Elo-only forecasts.
- Poisson-only forecasts.
- A standings/points-based baseline for season position forecasts.

Do not claim the model is superior without a fair, out-of-sample comparison.

---

## 9. User interface direction

### Design goal

A serious football analytics product: restrained, data-dense, readable, and professional. Avoid gambling-site styling, excessive gradients, neon effects, fake live indicators, or decorative AI branding.

### Proposed visual language

- Dark navy/charcoal base with slate surfaces.
- High-contrast text and readable data tables.
- A restrained accent color for probabilities and selected states.
- Green/red used only when they convey meaningful positive/negative status.
- Consistent club crests only when sourced from a permitted provider or asset source.
- Charts with clear legends, labels, tooltips, and accessible contrast.
- Desktop-first analytics layout that remains usable on mobile.

### Proposed pages

1. **Overview** — competition cards, recent forecast runs, next fixtures, data freshness, and leading probabilities.
2. **Competition page** — standings, title probabilities, expected final table, qualification and relegation outlook.
3. **UCL page** — league-phase table, qualification routes, play-off and knockout progression probabilities, winner forecast.
4. **Team page** — current standing, rating trend, recent results, upcoming fixtures, and forecast outlook.
5. **Match page** — home/draw/away probabilities, expected goals, score probability grid, and model factors.
6. **Model performance page** — backtest periods, metrics, calibration plots, model versions, and limitations.
7. **About / methodology** — data sources, update cadence, model descriptions, assumptions, and known limitations.

No page should display fabricated sample predictions as though they were live. Placeholder UI must be clearly labelled as demo data.

---

## 10. Local development setup

### Running locally

**Quickest way (Windows):** double-click `dev.cmd` in the project root. It sets everything up on first run, starts the backend and frontend in two windows, and opens the dashboard. Close those windows to stop.

Manual setup, if you prefer:

One-time setup (Windows, Git Bash; on PowerShell use `.venv\Scripts\activate`):

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

Copy `.env.example` to `.env` in the project root and fill in the keys.

Day-to-day commands:

| Task | Command (from the folder shown) |
|---|---|
| Start backend (http://localhost:8000) | `backend/`: `.venv/Scripts/python -m uvicorn app.main:app --reload` |
| Start frontend (http://localhost:5173) | `frontend/`: `npm run dev` |
| Backend tests | `backend/`: `.venv/Scripts/python -m pytest` |
| Backend lint / format / types | `backend/`: `.venv/Scripts/ruff check .` · `.venv/Scripts/ruff format .` · `.venv/Scripts/mypy app` |
| Frontend lint / build | `frontend/`: `npm run lint` · `npm run build` |

The frontend dev server forwards `/api/*` to the backend, so the browser never talks to a data provider directly.

### Required software

Install these before implementation:

| Tool | Why it is needed | Official download |
|---|---|---|
| Visual Studio Code | Main editor | <https://code.visualstudio.com/download> |
| Python 3.13 (64-bit) | Backend and forecasting engine | <https://www.python.org/downloads/windows/> |
| Node.js LTS | React/Vite frontend toolchain | <https://nodejs.org/en/download> |
| Git for Windows | Version control | <https://git-scm.com/install/windows> |

Recommended VS Code extensions:

- Python (Microsoft).
- Pylance (Microsoft).
- Python Debugger (Microsoft).
- ESLint.
- Prettier.
- Tailwind CSS IntelliSense.
- GitLens (optional).
- OpenAI Codex extension (optional coding agent).

### Accounts to create

| Account | Why | Official website |
|---|---|---|
| GitHub | Store source code and track changes | <https://github.com/> |
| API-Football | Test football data availability | <https://www.api-football.com/> |
| Supabase | Hosted PostgreSQL database | <https://supabase.com/> |
| Vercel | Frontend deployment when ready | <https://vercel.com/> |
| Railway | Possible backend deployment later | <https://railway.com/> |

Creating the accounts does not mean every service needs to be connected immediately. Do not create tables, deploy services, or purchase plans before the architecture and data requirements are confirmed.

### Coding assistant

OpenAI Codex can be used through a supported IDE extension or CLI by signing in with a ChatGPT account. Availability and usage limits depend on the current plan. Codex usage is not unlimited, and a cloud coding environment is not assumed to be available on every plan.

Official guide: <https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan>

An AI coding agent is an assistant, not an authority. It must not be allowed to invent API fields, skip tests, expose secrets, change the product scope, or silently rewrite the architecture.

### What is not required initially

- Cursor Pro or another paid IDE subscription.
- OpenAI API credits or an OpenAI API key.
- A GPU, CUDA, or local large language model.
- Docker (can be introduced if it solves a real environment problem).
- A paid Supabase plan.
- A paid football data plan before coverage is checked.
- A custom domain.
- Paid backend hosting during local development.

The Elo, Poisson, and Monte Carlo models proposed for V1 are conventional statistical computations. They do not require a dedicated GPU.

---

## 11. Environment variables and secret handling

Secrets must remain on the backend. Never put provider credentials in `frontend` environment variables that are exposed to the browser.

A future root/backend environment configuration may contain:

```env
# Football data provider
API_FOOTBALL_KEY=replace_me

# Supabase - backend only
SUPABASE_URL=replace_me
SUPABASE_SERVICE_ROLE_KEY=replace_me
SUPABASE_ANON_KEY=replace_me

# Application
APP_ENV=development
LOG_LEVEL=INFO
```

The frontend may only receive public, browser-safe configuration such as a public Supabase URL/key if the chosen architecture genuinely needs it. The service-role key must never reach the frontend.

Required safeguards:

- Commit `.env.example`, never `.env` or `.env.local`.
- Add secret files to `.gitignore` before the first commit.
- Rotate a key immediately if it is exposed.
- Do not paste credentials into chat, issue trackers, screenshots, or logs.
- Validate all environment variables at application startup.
- Use least-privilege credentials where the provider supports them.

---

## 12. Hosting and cost plan

The target is to keep initial development at **₹0 in additional project spending**, using local development and free tiers where practical. This is a target, not a promise that every production requirement will remain free.

| Service | Initial plan | Important caveat |
|---|---|---|
| API-Football | Free tier for prototype | Advertises 100 requests/day; historical seasons are limited by plan. Confirm current access and quota in the account dashboard. |
| Supabase | Free | Current published free limits include 500 MB database size; inactive free projects may be paused. Check current terms and usage limits. |
| Vercel | Hobby | Intended for personal/non-commercial use under current terms. Check the plan terms before commercial use. |
| Railway | Do not subscribe initially | Current pricing lists a Free plan with limited monthly credit and Hobby at a $5/month base fee including $5 of usage. Usage above the included amount can increase cost. |
| GitHub | Free account | Sufficient for a personal project repository. |
| Codex | Existing ChatGPT-plan access, subject to limits | Usage limits vary by plan; additional usage may have separate costs. |

Official pricing references:

- API-Football: <https://www.api-football.com/pricing>
- Supabase: <https://supabase.com/pricing>
- Vercel: <https://vercel.com/docs/plans/hobby>
- Railway: <https://docs.railway.com/pricing/plans>
- Codex access: <https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan>

No subscription should be purchased until a measured limitation requires it. Check prices and plan terms again at the point of purchase because providers can change them.

---

## 13. Development roadmap

Development is milestone-based. Each milestone must have a working, testable result before moving to the next one.

### Milestone 0 — Product and data validation

- Confirm V1 scope and the five competition identities.
- Inspect API-Football access for each competition and season.
- Verify 2026/27 fixtures, results, standings, status fields, and historical depth.
- Verify API quotas and permitted use.
- Compare available historical data against backtesting needs.
- Decide whether a second provider or a paid tier is necessary.

**Exit criteria:** A written data-coverage report exists. The project has not assumed coverage that has not been tested.

### Milestone 1 — Project foundation

- Create the Git repository and initial folder structure.
- Configure Python and Node environments.
- Add environment validation and safe secret handling.
- Add formatting, linting, and test commands.
- Define canonical competition/team/fixture data contracts.

**Exit criteria:** Backend and frontend launch locally; tests and lint checks run; secrets are not tracked by Git.

### Milestone 2 — Data ingestion

- Implement provider adapter.
- Fetch competition/season metadata.
- Fetch teams, fixtures, completed results, and standings where covered.
- Normalize provider data into canonical internal IDs.
- Add validation, deduplication, upserts, caching, and request logging.
- Store ingestion run status and provider errors.

**Exit criteria:** All five competitions can be imported without duplicate fixtures, invalid team mappings, or untracked API failures.

### Milestone 3 — Historical data and baseline models

- Import the verified historical seasons.
- Calculate chronological Elo ratings.
- Estimate Poisson attack/defence strengths and expected goals.
- Produce home/draw/away probabilities.
- Add unit tests with known small examples.

**Exit criteria:** Predictions are deterministic for a fixed input/configuration/seed and pass model tests. Historical calculations have no future-data leakage.

### Milestone 4 — Domestic league simulation

- Build generic league table and tiebreaker logic.
- Simulate remaining fixtures.
- Produce title, finishing-position, qualification, and relegation probabilities.
- Test each competition's season-specific rules.
- Test simulation stability with multiple seeds and simulation counts.

**Exit criteria:** All four domestic leagues produce internally consistent probability distributions. Position probabilities for each team sum to approximately 100%; title probabilities across teams sum to approximately 100%, allowing only rounding differences.

### Milestone 5 — Champions League simulation

- Encode the official 2026/27 UCL format and rules.
- Simulate remaining league-phase fixtures.
- Apply league-phase tiebreakers.
- Implement the play-off draw/path constraints and knockout rounds.
- Account for two-legged ties and the single-match final.
- Aggregate qualification and winner probabilities.

**Exit criteria:** Simulated UCL paths obey the competition rules and no impossible bracket progression is generated.

### Milestone 6 — Backtesting and calibration

- Build chronological walk-forward backtests.
- Calculate log loss, Brier score, calibration, and relevant ranking metrics.
- Compare Elo-only, Poisson-only, blended, and simple baselines.
- Review model behaviour by competition and matchweek.
- Store model version and backtest results.

**Exit criteria:** The model has documented out-of-sample performance and limitations. Do not publish performance claims without this evidence.

### Milestone 7 — Dashboard and API

- Define FastAPI response schemas.
- Build overview and competition pages.
- Add UCL progression visualizations.
- Add match and team detail views.
- Add model-performance and methodology pages.
- Display data freshness, forecast time, and model version.
- Add loading, empty, stale-data, and error states.

**Exit criteria:** The dashboard reads real persisted forecasts and never presents placeholder figures as live predictions.

### Milestone 8 — Deployment and monitoring

- Deploy frontend to an appropriate Vercel plan.
- Deploy backend to Railway or another suitable host only after measuring runtime needs.
- Configure production secrets securely.
- Add health checks and structured logs.
- Set a controlled refresh schedule.
- Monitor API quotas, database use, forecast failures, and hosting costs.

**Exit criteria:** A production-like deployment updates forecasts safely, exposes no secrets, and reports failures clearly.

---

## 14. API design proposal

**Implemented** (Milestone 7). The reference with response shapes and dashboard rules is `docs/api.md`. The live, field-by-field docs are at `/docs` on the running backend. Additions beyond this table: `/health/ready`, `/fixtures/{id}`, and a `preview` query parameter.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `GET` | `/api/v1/competitions` | List supported competitions |
| `GET` | `/api/v1/competitions/{competition_id}/seasons/{season_id}/overview` | Competition summary and latest forecast metadata |
| `GET` | `/api/v1/competitions/{competition_id}/seasons/{season_id}/standings` | Current table/league-phase table |
| `GET` | `/api/v1/competitions/{competition_id}/seasons/{season_id}/forecast` | Latest season forecast |
| `GET` | `/api/v1/fixtures/upcoming` | Upcoming fixtures |
| `GET` | `/api/v1/fixtures/{fixture_id}/forecast` | Match probabilities |
| `GET` | `/api/v1/teams/{team_id}` | Team profile and rating summary |
| `GET` | `/api/v1/teams/{team_id}/forecast-history` | Team forecast history |
| `GET` | `/api/v1/models/versions` | Model versions |
| `GET` | `/api/v1/models/performance` | Backtest metrics and calibration summaries |
| `GET` | `/api/v1/forecasts/{run_id}` | Forecast run details |

Forecast-generation and ingestion endpoints should be protected. They must not be publicly callable in a way that lets visitors exhaust provider quotas or trigger expensive simulations.

---

## 15. Testing and quality gates

### Data tests

- Provider payload schema validation.
- Competition and team mapping tests.
- Duplicate fixture detection.
- Missing and malformed score handling.
- Match status normalization.
- UTC timestamp handling.
- Standings consistency checks.
- Provider quota and failure handling.

### Model tests

- Elo ratings update in chronological order.
- Match probabilities are in the range 0–1 and sum to approximately 1.
- Poisson probabilities are non-negative and normalized within a documented goal range.
- Monte Carlo runs are reproducible with a fixed seed.
- Position probabilities sum to approximately 1 for each team.
- League title probabilities sum to approximately 1 across the teams in the competition.
- Completed matches are not resimulated as future fixtures.
- Tiebreakers and UCL progression obey the relevant rules.
- Backtests do not use future data.

### Product quality gates

- No hardcoded live forecasts.
- No silently stale data.
- No secrets in Git history.
- No unhandled provider errors that appear as valid predictions.
- No model-performance claims without test results.
- All forecast outputs show their update time and model version.

---

## 16. Definition of done for V1

V1 is considered complete when:

- All five selected competitions are supported for the 2026/27 season, subject to verified provider coverage.
- Fixtures, results, and standings are imported and validated.
- Domestic league forecasts are generated by the tested Elo/Poisson/Monte Carlo pipeline.
- UCL forecasts follow the verified 2026/27 competition format.
- Match and season probabilities are stored with timestamps and model versions.
- Historical backtesting and calibration results are available.
- The dashboard reads actual stored predictions.
- Users can see data freshness, methodology, and known limitations.
- Tests cover the critical data, model, and competition-rule paths.
- The application can be run locally from documented instructions.
- Production deployment, if enabled, keeps keys secret and respects data-provider terms and quotas.

---

## 17. Risks and known limitations

| Risk | Why it matters | Mitigation |
|---|---|---|
| Insufficient historical API coverage | Weak backtesting and unstable ratings | Verify coverage before selecting the provider/plan; compare alternatives |
| API rate limits | Data may become stale or incomplete | Cache, batch, refresh selectively, log request usage |
| Data errors or postponed fixtures | Incorrect standings and simulations | Validate statuses, scores, and table consistency |
| Team changes/promotions | Ratings may not be comparable | Document initialization and promotion policies |
| Cross-league UCL ratings | Clubs play different domestic schedules | Define and test a shared-rating approach; report limitations |
| Model overconfidence | Misleading probabilities | Backtest, calibrate, compare baselines, show uncertainty |
| Data leakage | Backtests look better than reality | Strict chronological snapshots and automated leakage tests |
| Competition rule changes | Invalid qualification or bracket outputs | Store season-specific official rules and verify them |
| Free-tier changes | Unexpected cost or service interruption | Recheck current terms and keep provider adapters replaceable |
| Simulation randomness | Small probability fluctuations between runs | Store seeds and test convergence at multiple simulation counts |

The model will not know the future. Injuries, managerial changes, transfers, tactical shifts, and unexpected events may be absent or only indirectly reflected. Forecast limitations must be stated rather than hidden.

---

## 18. Working rules for AI coding agents

When using Codex or another coding assistant on this repository, follow these rules:

1. Read this README and the relevant docs before changing files.
2. Work on one milestone or clearly scoped task at a time.
3. Do not silently expand V1 scope.
4. Do not invent provider endpoints, response fields, competition IDs, historical coverage, or API limits. Check official documentation or inspect a real response.
5. Do not hardcode current standings, teams, fixtures, or forecasts as production data.
6. Keep secrets out of source code, browser bundles, logs, commits, and generated documentation.
7. Separate provider-specific code from internal domain models.
8. Add or update tests whenever data transformations, model logic, or competition rules change.
9. Explain important tradeoffs and list files changed.
10. Run relevant tests and lint/type checks before claiming a task is complete.
11. Do not change the model methodology or database schema without explaining the reason and updating the documentation.
12. Prefer the simplest approach that meets a verified requirement.
13. Never claim a forecast is accurate or validated unless the corresponding backtest supports that claim.
14. Ask before adding a paid service, paid API tier, or recurring expense.

A coding agent may generate implementation code, but the project owner is responsible for reviewing the changes and understanding the system.

---

## 19. Open decisions before implementation

These decisions must be resolved during Milestone 0 and early architecture work:

- Does API-Football's free plan expose enough 2026/27 data and historical seasons for all five competitions?
- How many historical seasons are available for each competition, and are all required match fields present?
- Is a second provider required for historical results or specific competition coverage?
- Which exact qualification positions should be displayed for each domestic league in 2026/27?
- What source will be treated as authoritative for competition-specific tiebreakers and UCL draw constraints?
- How should promoted teams and clubs with limited cross-league history be initialized in Elo?
- Should V1 refresh forecasts automatically after every completed match, or on a scheduled daily/manual basis?
- What minimum backtest performance and calibration standards should be required before forecasts are labelled production-ready?
- Which backend host is the best fit after measuring simulation runtime and expected traffic?

Do not hide unresolved decisions in code. Record them in `docs/decisions.md` with the options considered and the chosen rationale.

---

## 20. Reference links

### Football data

- API-Football: <https://www.api-football.com/>
- API-Football documentation: <https://www.api-football.com/documentation-v3>
- API-Football pricing: <https://www.api-football.com/pricing>
- Football-data.org: <https://www.football-data.org/>
- Football-data.org documentation: <https://www.football-data.org/documentation/quickstart>
- UEFA Champions League: <https://www.uefa.com/uefachampionsleague/>

### Development tools

- Visual Studio Code: <https://code.visualstudio.com/>
- Python: <https://www.python.org/>
- Node.js: <https://nodejs.org/>
- Git: <https://git-scm.com/>
- GitHub: <https://github.com/>
- OpenAI Codex with ChatGPT plans: <https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan>

### Infrastructure

- Supabase: <https://supabase.com/>
- Supabase pricing: <https://supabase.com/pricing>
- Vercel: <https://vercel.com/>
- Vercel Hobby plan: <https://vercel.com/docs/plans/hobby>
- Railway: <https://railway.com/>
- Railway pricing: <https://docs.railway.com/pricing/plans>

---

## 21. Current project status

**Current phase: Milestone 7 (API) complete → dashboard to be built from the project owner's design.**

Done so far:

- Backend skeleton (FastAPI health endpoint, config validation, domain models, provider clients, tests).
- API-Football Free: **no 2026/27 access**, history 2022–2024 only. See `docs/milestone-0-coverage-report.md`.
- **Primary provider: football-data.org (free tier).** It fully covers all five competitions for 2026/27, and history is available for 2023–2025. See `docs/milestone-0-football-data-org-report.md` and `docs/decisions.md` OD-001.
- Milestone 1: Git repo, backend virtualenv, lint/format/type/test tooling, validated domain contracts (`backend/app/domain/models.py`, documented in `docs/data-dictionary.md`), and a React + Vite + Tailwind frontend shell connected to the backend.
- Milestone 2: Supabase schema with migrations and row-level security (`backend/migrations/`); a normalizer that handles extra time and shootouts correctly; idempotent, audited ingestion; and a standings cross-check. **6,431 matches across 20 competition-seasons (2023/24–2026/27) are imported and validated: 5,266 played and 1,164 still to play** (one cancelled). See `docs/architecture.md` and `docs/known-data-issues.md`.

- Milestone 3: chronological Elo ratings (with an ordered-logit draw model) and a time-weighted Poisson goal model, both with built-in leakage guards and tests against synthetic leagues with known strengths. **Not yet validated.** A first sanity check beats base rates; see `docs/model-methodology.md`. Developer preview: `backend/scripts/preview_models.py`.

- Milestone 4: 2026/27 rules for the four leagues (`backend/rules/2026/`, secondary source, flagged as such), a tiebreaker engine covering each league's rules (including head-to-head mini-leagues and Serie A play-offs), a Monte Carlo season simulator (10,000 runs in about 1–2 s per league) with a fixture-list completeness check, and reproducible, unpublished forecast storage. Run: `backend/scripts/run_forecast.py`.

- Milestone 5: Champions League simulator built from the **official UEFA 2026/27 regulations** (Arts. 17–22, primary source): league phase with all 10 tiebreakers, play-offs, the fixed bracket, two-legged ties, extra time, penalties and the neutral final. Every simulated bracket is audited against the rules in tests. The tiebreak engine reproduces 8 official final tables, including head-to-head cases, and revealed that the provider's own standings ignore head-to-head (`docs/known-data-issues.md` #5). **Open item:** conditioning on the real knockout draw must be built before the play-off draw in late January 2027.

- Milestone 6: walk-forward backtesting (weekly refits, tuned on 2024/25, tested once on 2,060 later matches). Poisson beats Elo significantly and both beat base rates; tuning and blending gave no measurable gain on unseen data. The production config is v0.2.0 (`backend/app/models/config.py`): Poisson with learned priors for promoted/UCL-only clubs, plus team-strength uncertainty in season simulations. Results: `docs/backtest-report.md`, stored in `backtest_runs`; decision OD-005.

- Pre-Milestone 7 fixes: EPL and Bundesliga rules verified against the official 2026/27 documents (this corrected the Bundesliga's head-to-head criterion to the aggregate score); UCL simulator now conditions on the real knockout draw and results (validated by replaying the real 2025/26 knockout phase) with an optional draw file; strength uncertainty extended to the UCL (model v0.2.1).

- Milestone 7 (API): read-only FastAPI v1 with competitions, standings, season forecasts (incl. UCL rounds), upcoming fixtures, fixture detail with scorelines, team pages, forecast history, model versions and backtest performance. Published-only by default, with `?preview=true` for clearly flagged unpublished runs; provenance and data freshness on every response. Publishing goes through `backend/scripts/publish_run.py` (quality gates). Reference: `docs/api.md`.

**Next action:** build the dashboard from the project owner's own design (the frontend is intentionally still a shell), then Milestone 8 (deployment).

---

*Final Whistle is an independent football analytics project. It is not affiliated with, endorsed by, or sponsored by UEFA, the Premier League, La Liga, Bundesliga, Serie A, or any football club or data provider.*
