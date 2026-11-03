import { useApi } from './useApi'
import { api, type CompetitionCode, type CompetitionSummary, type SeasonForecast, type Timeline } from '../services/api'

export interface CompetitionBundle {
  summary: CompetitionSummary
  forecast?: SeasonForecast
  timeline?: Timeline
}

/** Every competition with its latest published forecast and title timeline. */
export function useAllCompetitions() {
  return useApi(async () => {
    const comps = await api.competitions()
    const out = await Promise.all(
      comps.map(async (summary): Promise<CompetitionBundle> => {
        const year = summary.current_season
        if (!year || !summary.latest_published_run) return { summary }
        const [forecast, timeline] = await Promise.all([
          api.forecast(summary.code, year).catch(() => undefined),
          api.timeline(summary.code, year).catch(() => undefined),
        ])
        return { summary, forecast, timeline }
      }),
    )
    return new Map<CompetitionCode, CompetitionBundle>(out.map((b) => [b.summary.code, b]))
  }, [])
}

export function useCompetition(code: CompetitionCode) {
  return useApi(async () => {
    const comps = await api.competitions()
    const summary = comps.find((c) => c.code === code)
    if (!summary?.current_season) throw new Error('No season data for this competition yet.')
    const year = summary.current_season
    const [forecast, timeline, standings] = await Promise.all([
      api.forecast(code, year),
      api.timeline(code, year).catch(() => undefined),
      api.standings(code, year).catch(() => undefined),
    ])
    return { summary, forecast, timeline, standings }
  }, [code])
}
