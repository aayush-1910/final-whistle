import type { CompetitionCode, TeamRef, TeamForecast } from '../services/api'

export const COMPETITION_LABEL: Record<CompetitionCode, string> = {
  EPL: 'Premier League',
  LA_LIGA: 'La Liga',
  BUNDESLIGA: 'Bundesliga',
  SERIE_A: 'Serie A',
  UCL: 'UEFA Champions League',
}

export const COMPETITION_SHORT: Record<CompetitionCode, string> = {
  EPL: 'Premier League',
  LA_LIGA: 'La Liga',
  BUNDESLIGA: 'Bundesliga',
  SERIE_A: 'Serie A',
  UCL: 'Champions League',
}

/** Probability (0–1) as a percentage with one decimal. Tiny non-zero values say so. */
export function pct(p: number | null | undefined, digits = 1): string {
  if (p == null || Number.isNaN(p)) return '–'
  if (p > 0 && p < 0.001) return '<0.1%'
  if (p < 1 && p > 0.999) return '>99.9%'
  return `${(p * 100).toFixed(digits)}%`
}

/** Percentage-point change, signed. */
export function pp(delta: number): string {
  const v = delta * 100
  return `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}pp`
}

export function teamName(t: TeamRef): string {
  return t.short_name || t.name
}

const dateFmt = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})
const timeFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' })
const fullFmt = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** Local date, e.g. "Sun, 18 Jan" (kickoffs are stored in UTC). */
export const fmtDate = (iso: string) => dateFmt.format(new Date(iso))
export const fmtTime = (iso: string) => timeFmt.format(new Date(iso))
export const fmtDateTime = (iso: string) => fullFmt.format(new Date(iso))

export function timeAgo(iso: string, now = Date.now()): string {
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  const d = Math.floor(s / 86400)
  return d === 1 ? 'yesterday' : `${d} days ago`
}

/** The "title" probability: league champion, or lifting the trophy in the UCL. */
export function titleProb(t: TeamForecast, code: CompetitionCode): number {
  return code === 'UCL' ? (t.round_probs?.winner ?? 0) : (t.zone_probs.champion ?? 0)
}

export const ROUND_LABEL: Record<string, string> = {
  round_of_16: 'Round of 16',
  quarter_finals: 'Quarter-finals',
  semi_finals: 'Semi-finals',
  final: 'Final',
  winner: 'Winner',
}

export const ROUND_SHORT: Record<string, string> = {
  round_of_16: 'R16',
  quarter_finals: 'QF',
  semi_finals: 'SF',
  final: 'Final',
  winner: 'Win',
}

export const STAGE_LABEL: Record<string, string> = {
  regular_season: 'League',
  league_stage: 'League phase',
  playoffs: 'Knockout play-offs',
  last_16: 'Round of 16',
  quarter_finals: 'Quarter-final',
  semi_finals: 'Semi-final',
  final: 'Final',
}
