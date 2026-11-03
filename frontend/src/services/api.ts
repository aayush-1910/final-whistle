/**
 * Backend API client. All requests go to the FastAPI backend via the Vite
 * proxy (/api → localhost:8000). Never call football data providers from
 * the browser — keys stay on the backend.
 *
 * Only PUBLISHED forecasts are requested (no ?preview=true), so everything the
 * dashboard shows has passed the publishing gates.
 */

export type CompetitionCode = 'EPL' | 'LA_LIGA' | 'BUNDESLIGA' | 'SERIE_A' | 'UCL'
export const COMPETITION_CODES: CompetitionCode[] = ['EPL', 'UCL', 'LA_LIGA', 'BUNDESLIGA', 'SERIE_A']

export interface TeamRef {
  id: number
  name: string
  short_name: string | null
  tla: string | null
  crest_url: string | null
}

export interface Freshness {
  last_ingested_at: string | null
  last_ingestion_status: string | null
  is_stale: boolean
  stale_after_hours: number
}

export interface RunInfo {
  run_id: number
  model_name: string
  model_version: string
  data_cutoff: string
  run_at: string
  simulation_count: number
  seed: number
  code_version: string | null
  is_published: boolean
  is_backfill: boolean
  rules_source_quality: string | null
  notes: string[]
}

export interface CompetitionSummary {
  code: CompetitionCode
  name: string
  format: string
  country: string | null
  emblem_url: string | null
  current_season: number | null
  season_label: string | null
  freshness: Freshness
  latest_published_run: RunInfo | null
  preview_run_available: boolean
}

export interface StandingRow {
  position: number
  team: TeamRef
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  goal_difference: number
  points: number
  form: string[]
}

export interface StandingsResponse {
  competition: CompetitionCode
  season: number
  season_label: string
  ordering_note: string
  freshness: Freshness
  rows: StandingRow[]
}

export interface Zone {
  key: string
  label: string
  first_position: number
  last_position: number
}

export interface TeamForecast {
  team: TeamRef
  current_points: number
  played: number
  expected_points: number
  expected_position: number
  position_probs: number[]
  zone_probs: Record<string, number>
  round_probs: Record<string, number> | null
}

export interface SeasonForecast {
  competition: CompetitionCode
  season: number
  season_label: string
  run: RunInfo
  freshness: Freshness
  zones: Zone[]
  rounds: string[] | null
  teams: TeamForecast[]
  disclaimer: string
}

export interface MatchForecast {
  p_home: number
  p_draw: number
  p_away: number
  xg_home: number
  xg_away: number
  run_id: number
  model_version: string
  data_cutoff: string
  is_published: boolean
}

export interface Fixture {
  id: number
  competition: CompetitionCode
  season: number
  stage: string
  matchday: number | null
  kickoff_utc: string | null
  status: string
  home: TeamRef
  away: TeamRef
  home_score: number | null
  away_score: number | null
  duration: string
  home_penalties: number | null
  away_penalties: number | null
  forecast: MatchForecast | null
}

export interface FixtureDetail extends Fixture {
  likely_scorelines: { home: number; away: number; probability: number }[]
  score_matrix: number[][] | null
  disclaimer: string
}

export interface TeamDetail {
  team: TeamRef
  country: string | null
  seasons: { competition: CompetitionCode; season: number; position: number | null; played: number; points: number }[]
  recent_results: Fixture[]
  upcoming_fixtures: Fixture[]
}

export interface ForecastHistory {
  team: TeamRef
  competition: CompetitionCode
  season: number
  points: {
    run_id: number
    run_at: string
    data_cutoff: string
    model_version: string
    is_published: boolean
    expected_position: number
    expected_points: number
    zone_probs: Record<string, number>
    round_probs: Record<string, number> | null
  }[]
}

export interface TimelinePoint {
  run_id: number
  data_cutoff: string
  matchday: number
  is_published: boolean
  is_backfill: boolean
  probs: Record<string, number>
  expected_points: Record<string, number>
}

export interface Timeline {
  competition: CompetitionCode
  season: number
  metric: 'champion' | 'winner'
  teams: TeamRef[]
  points: TimelinePoint[]
}

export interface ModelVersion {
  model_name: string
  model_version: string
  runs: number
  published_runs: number
  first_run_at: string
  last_run_at: string
  is_current: boolean
}

export interface Backtest {
  backtest_id: number
  kind: 'match' | 'season'
  model_version: string
  run_at: string
  tuning_window: Record<string, unknown>
  test_window: Record<string, unknown>
  params: Record<string, unknown>
  metrics: Record<string, unknown>
}

export interface Performance {
  current_model_version: string
  match_level: Backtest | null
  season_level: Backtest | null
  report: string
}

export interface DataStatus {
  competitions: {
    code: CompetitionCode
    name: string
    season: number | null
    fixtures_total: number
    fixtures_played: number
    fixtures_remaining: number
    freshness: Freshness
    latest_run_id: number | null
    latest_run_cutoff: string | null
    latest_run_published: boolean | null
    runs_total: number
    runs_published: number
  }[]
  recent_ingestions: {
    id: number
    competition: CompetitionCode | null
    season: number | null
    started_at: string
    finished_at: string | null
    status: string
    request_count: number
    fixtures_inserted: number
    fixtures_updated: number
    issues: number
    consistency_ok: boolean | null
    error: string | null
  }[]
}

export interface HealthResponse {
  status: string
  service: string
  database?: string
}

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Small in-memory cache: pages share data (e.g. forecasts) without refetching.
const cache = new Map<string, { at: number; promise: Promise<unknown> }>()
const TTL_MS = 60_000

export function get<T>(path: string, { fresh = false } = {}): Promise<T> {
  const hit = cache.get(path)
  if (!fresh && hit && Date.now() - hit.at < TTL_MS) return hit.promise as Promise<T>
  const promise = fetch(`/api/v1${path}`).then(async (res) => {
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = (await res.json()) as { detail?: unknown }
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        /* not JSON */
      }
      throw new ApiError(res.status, detail)
    }
    return (await res.json()) as T
  })
  promise.catch(() => cache.delete(path))
  cache.set(path, { at: Date.now(), promise })
  return promise
}

export const api = {
  health: () => get<HealthResponse>('/health/ready', { fresh: true }),
  competitions: () => get<CompetitionSummary[]>('/competitions'),
  standings: (code: CompetitionCode, year: number) =>
    get<StandingsResponse>(`/competitions/${code}/seasons/${year}/standings`),
  forecast: (code: CompetitionCode, year: number) =>
    get<SeasonForecast>(`/competitions/${code}/seasons/${year}/forecast`),
  timeline: (code: CompetitionCode, year: number) =>
    get<Timeline>(`/competitions/${code}/seasons/${year}/timeline`),
  upcoming: (days = 7, competition?: CompetitionCode) =>
    get<Fixture[]>(`/fixtures/upcoming?days=${days}${competition ? `&competition=${competition}` : ''}`),
  fixture: (id: number) => get<FixtureDetail>(`/fixtures/${id}`),
  team: (id: number) => get<TeamDetail>(`/teams/${id}`),
  teamHistory: (id: number, code: CompetitionCode, season: number) =>
    get<ForecastHistory>(`/teams/${id}/forecast-history?competition=${code}&season=${season}`),
  modelVersions: () => get<ModelVersion[]>('/models/versions'),
  performance: () => get<Performance>('/models/performance'),
  dataStatus: () => get<DataStatus>('/data/status'),
}
