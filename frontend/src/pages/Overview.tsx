import { useMemo, useState } from 'react'
import { ArrowDownIcon, ArrowUpIcon, BarsIcon, CalendarIcon, ChevronRightIcon, CrownIcon, RefreshIcon, TrendIcon } from '../components/icons'
import { TimelineChart } from '../components/TimelineChart'
import {
  Card,
  CardHeader,
  CompetitionSelect,
  Crest,
  Disclaimer,
  Emblem,
  EmptyNote,
  ErrorNote,
  LoadingRows,
  Meter,
  ProbPill,
  RunMeta,
  Skeleton,
  ViewAll,
} from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAllCompetitions, type CompetitionBundle } from '../hooks/useSeasonData'
import { COMPETITION_LABEL, COMPETITION_SHORT, fmtDate, fmtTime, pct, pp, teamName, timeAgo, titleProb } from '../lib/format'
import { api, COMPETITION_CODES, type CompetitionCode, type Fixture, type TeamRef } from '../services/api'

type Bundles = Map<CompetitionCode, CompetitionBundle>

const metricWord = (code: CompetitionCode) => (code === 'UCL' ? 'Win probability' : 'Title probability')

// ---------------------------------------------------------------------------
// The Verdict
// ---------------------------------------------------------------------------
function Verdict({ bundles }: { bundles: Bundles }) {
  let best: { code: CompetitionCode; team: TeamRef; p: number } | undefined
  let run
  for (const [code, b] of bundles) {
    const top = b.forecast?.teams.reduce<{ team: TeamRef; p: number } | undefined>((acc, t) => {
      const p = titleProb(t, code)
      return !acc || p > acc.p ? { team: t.team, p } : acc
    }, undefined)
    if (top && (!best || top.p > best.p)) {
      best = { code, ...top }
      run = b.forecast!.run
    }
  }
  return (
    <section className="card relative overflow-hidden p-6">
      {/* Atmosphere only: the trophy artwork will go here later. */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_85%_20%,rgba(139,92,246,0.45),transparent_55%),radial-gradient(ellipse_at_100%_100%,rgba(109,40,217,0.35),transparent_50%)]" />
      <CrownIcon
        size={190}
        strokeWidth={0.6}
        className="pointer-events-none absolute -top-2 right-4 text-brand-300/15"
      />
      <div className="relative">
        <div className="flex flex-wrap items-center gap-3">
          <BarsIcon size={20} className="text-brand-400" />
          <span className="text-[17px] font-bold tracking-wide text-white">THE VERDICT</span>
          <span className="rounded-full border border-brand-500/60 bg-brand-600/25 px-3 py-0.5 text-[11px] font-semibold tracking-wide text-brand-300">
            WEEKLY FORECAST
          </span>
        </div>
        <h2 className="mt-4 text-[30px] leading-tight font-bold tracking-tight text-white">Who wins the league?</h2>
        <p className="mt-1.5 max-w-[340px] text-[14px] text-slate-300">
          The model’s current highest-rated title contender across the five tracked competitions.
        </p>
        {best && run ? (
          <>
            <div className="mt-6 flex flex-wrap items-center gap-6">
              <a href={`#/teams/${best.team.id}`} className="flex items-center gap-4">
                <Crest team={best.team} size={64} />
                <span>
                  <span className="block text-[22px] font-semibold text-white">{teamName(best.team)}</span>
                  <span className="block text-[14px] text-slate-400">{COMPETITION_LABEL[best.code]}</span>
                </span>
              </a>
              <span className="hidden h-16 w-px bg-ink-600 sm:block" />
              <span>
                <span className="tabular block bg-gradient-to-r from-brand-400 to-brand-300 bg-clip-text text-[44px] leading-none font-bold text-transparent">
                  {pct(best.p)}
                </span>
                <span className="mt-1.5 block text-[14px] text-slate-300">{metricWord(best.code)}</span>
              </span>
            </div>
            <RunMeta run={run} className="mt-6 border-t border-ink-700/70 pt-4" />
          </>
        ) : (
          <EmptyNote>No published forecast yet.</EmptyNote>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Competitions at a Glance
// ---------------------------------------------------------------------------
function Glance({ bundles }: { bundles: Bundles }) {
  const order: CompetitionCode[] = ['EPL', 'UCL', 'LA_LIGA', 'BUNDESLIGA', 'SERIE_A']
  return (
    <Card>
      <CardHeader icon={<BarsIcon />} title="Competitions at a Glance" action={<ViewAll href="#/competitions" />} />
      <div className="grid gap-3 sm:grid-cols-6">
        {order.map((code, i) => {
          const b = bundles.get(code)
          const leader = b?.forecast?.teams
            .map((t) => ({ t, p: titleProb(t, code) }))
            .sort((a, z) => z.p - a.p)[0]
          return (
            <a
              key={code}
              href={code === 'UCL' ? '#/ucl' : `#/competitions/${code}`}
              className={`group flex flex-col rounded-xl border border-ink-700 bg-ink-800/50 p-3.5 transition-colors hover:border-brand-500/60 ${
                i < 3 ? 'sm:col-span-2' : 'sm:col-span-3'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Emblem url={b?.summary.emblem_url} code={code} size={30} />
                <span className="flex-1 text-[14px] leading-tight font-semibold text-white">
                  {code === 'UCL' ? 'UEFA Champions League' : COMPETITION_SHORT[code]}
                </span>
                <ChevronRightIcon size={16} className="text-slate-500 group-hover:text-brand-300" />
              </div>
              <p className="mt-auto truncate pt-3 text-[13px] text-slate-300">
                {leader ? `${teamName(leader.t.team)} (${pct(leader.p)})` : 'No forecast yet'}
              </p>
              <Meter value={leader?.p ?? 0} className="mt-2" />
            </a>
          )
        })}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Title race table
// ---------------------------------------------------------------------------
function TitleRace({ bundles }: { bundles: Bundles }) {
  const [code, setCode] = useState<CompetitionCode>('EPL')
  const f = bundles.get(code)?.forecast
  const rows = f?.teams
    .map((t) => ({ t, p: titleProb(t, code) }))
    .sort((a, b) => b.p - a.p || a.t.expected_position - b.t.expected_position)
    .slice(0, 5)
  return (
    <Card>
      <CardHeader
        icon={<CrownIcon />}
        title={`${COMPETITION_SHORT[code]} ${code === 'UCL' ? 'Race' : 'Title Race'}`}
        subtitle={
          f
            ? `${code === 'UCL' ? 'Probability of lifting the trophy' : 'Title winning probability'} · ${f.run.simulation_count.toLocaleString()} simulations`
            : undefined
        }
        action={<CompetitionSelect value={code} onChange={setCode} />}
      />
      {!rows ? (
        <EmptyNote>No published forecast for this competition yet.</EmptyNote>
      ) : (
        <table className="w-full text-[14px]">
          <thead>
            <tr className="border-b border-ink-700 text-left text-[13px] text-slate-400">
              <th className="w-8 py-2 font-medium">#</th>
              <th className="py-2 font-medium">Team</th>
              <th className="py-2 text-center font-medium">{code === 'UCL' ? 'Win Prob.' : 'Title Prob.'}</th>
              <th className="py-2 text-right font-medium">{code === 'UCL' ? 'Final' : 'Exp. Pts'}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ t, p }, i) => (
              <tr key={t.team.id} className="border-b border-ink-700/50 last:border-0">
                <td className="py-2.5 text-slate-300">{i + 1}</td>
                <td className="py-2.5">
                  <a href={`#/teams/${t.team.id}`} className="flex items-center gap-3 text-white hover:text-brand-300">
                    <Crest team={t.team} size={24} />
                    {teamName(t.team)}
                  </a>
                </td>
                <td className="py-2.5 text-center">
                  <ProbPill p={p}>{pct(p)}</ProbPill>
                </td>
                <td className="tabular py-2.5 text-right text-slate-200">
                  {code === 'UCL' ? pct(t.round_probs?.final) : t.expected_points.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------
function TimelineCard({ bundles }: { bundles: Bundles }) {
  const [code, setCode] = useState<CompetitionCode>('EPL')
  const tl = bundles.get(code)?.timeline
  return (
    <Card>
      <CardHeader
        icon={<TrendIcon />}
        title={code === 'UCL' ? 'Win Probability Timeline' : 'Title Probability Timeline'}
        subtitle="How the model’s forecast has changed this season."
        action={<CompetitionSelect value={code} onChange={setCode} />}
      />
      {tl ? <TimelineChart timeline={tl} /> : <EmptyNote>No published forecasts yet.</EmptyNote>}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Next big fixtures
// ---------------------------------------------------------------------------
function useBigFixtures(bundles: Bundles) {
  const upcoming = useApi(() => api.upcoming(14), [])
  const fixtures = useMemo(() => {
    if (!upcoming.data) return undefined
    const strength = new Map<string, number>()
    for (const [code, b] of bundles)
      for (const t of b.forecast?.teams ?? []) strength.set(`${code}:${t.team.id}`, titleProb(t, code))
    const score = (f: Fixture) =>
      (strength.get(`${f.competition}:${f.home.id}`) ?? 0) + (strength.get(`${f.competition}:${f.away.id}`) ?? 0)
    // "Big" = the two clubs' combined title chances; one per pairing.
    return [...upcoming.data].sort((a, b) => score(b) - score(a)).slice(0, 3)
  }, [upcoming.data, bundles])
  return { ...upcoming, fixtures }
}

function NextFixtures({ bundles }: { bundles: Bundles }) {
  const { fixtures, error } = useBigFixtures(bundles)
  return (
    <Card>
      <CardHeader
        icon={<CalendarIcon />}
        title="Next Big Fixtures"
        subtitle="Upcoming matches across all competitions."
        action={<ViewAll href="#/match-predictor" />}
      />
      {error ? (
        <ErrorNote error={error} />
      ) : !fixtures ? (
        <LoadingRows rows={3} />
      ) : fixtures.length === 0 ? (
        <EmptyNote>No fixtures in the next 14 days.</EmptyNote>
      ) : (
        <ul className="divide-y divide-ink-700/60">
          {fixtures.map((f) => (
            <li key={f.id}>
              <a href={`#/match-predictor/${f.id}`} className="flex items-center gap-3 py-3 hover:bg-ink-800/40">
                <Emblem url={bundles.get(f.competition)?.summary.emblem_url} code={f.competition} size={24} />
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  <Crest team={f.home} size={26} />
                  <span className="truncate text-[14px] text-white">{teamName(f.home)}</span>
                </span>
                <span className="text-[12px] text-slate-500">vs</span>
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  <Crest team={f.away} size={26} />
                  <span className="truncate text-[14px] text-white">{teamName(f.away)}</span>
                </span>
                {f.kickoff_utc && (
                  <span className="shrink-0 text-right text-[12px] leading-snug text-slate-400">
                    {fmtDate(f.kickoff_utc)}
                    <br />
                    {fmtTime(f.kickoff_utc)}
                  </span>
                )}
              </a>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Model insights
// ---------------------------------------------------------------------------
interface Mover {
  code: CompetitionCode
  team: TeamRef
  before: number
  after: number
  fromMd: number
  toMd: number
  at: string
}

function movers(bundles: Bundles, back: number): Mover[] {
  const out: Mover[] = []
  for (const [code, b] of bundles) {
    const pts = b.timeline?.points
    if (!pts || pts.length < 2) continue
    const last = pts[pts.length - 1]
    const prev = pts[Math.max(0, pts.length - 1 - back)]
    const teams = new Map(b.timeline!.teams.map((t) => [String(t.id), t]))
    for (const id of Object.keys(last.probs)) {
      out.push({
        code,
        team: teams.get(id)!,
        before: prev.probs[id] ?? 0,
        after: last.probs[id],
        fromMd: prev.matchday,
        toMd: last.matchday,
        at: last.data_cutoff,
      })
    }
  }
  return out.sort((a, b) => Math.abs(b.after - b.before) - Math.abs(a.after - a.before))
}

function Insights({ bundles }: { bundles: Bundles }) {
  const perf = useApi(() => api.performance(), [])
  const sims = [...bundles.values()].find((b) => b.forecast)?.forecast?.run.simulation_count
  const overall = (perf.data?.match_level?.metrics as { overall?: Record<string, Record<string, number>> })?.overall
  const prod = overall?.['Poisson (tuned)'] ?? Object.entries(overall ?? {}).find(([k]) => k.startsWith('Poisson'))?.[1]
  const riser = movers(bundles, 5).find((m) => m.after - m.before > 0 && m.after >= 0.05)
  const tiles = [
    { value: sims ? sims.toLocaleString() : '–', label: 'Simulations', hint: 'Season simulations per forecast' },
    {
      value: prod ? pct(prod.ece) : '–',
      label: 'Calibration error',
      hint: 'Average gap between predicted and observed frequencies on unseen matches (lower is better)',
    },
    {
      value: prod ? prod.brier.toFixed(3) : '–',
      label: 'Brier Score',
      hint: 'Win/draw/loss Brier score on unseen matches (lower is better; always guessing league averages scores 0.645)',
    },
  ]
  return (
    <Card>
      <CardHeader icon={<BarsIcon />} title="Model Insights" action={<ViewAll href="#/model" label="Details" />} />
      <div className="grid grid-cols-3 gap-2.5">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl border border-ink-700 bg-ink-800/50 px-2 py-3.5 text-center" title={t.hint}>
            <p className="tabular text-[22px] font-semibold text-white">{t.value}</p>
            <p className="mt-0.5 text-[12px] leading-tight text-slate-400">{t.label}</p>
          </div>
        ))}
      </div>
      {riser && (
        <div className="mt-3 flex items-center gap-3 rounded-xl border border-brand-500/40 bg-gradient-to-r from-brand-700/40 to-brand-600/20 px-4 py-3">
          <TrendIcon className="shrink-0 text-brand-300" />
          <p className="text-[13px] text-slate-100">
            {teamName(riser.team)}’s {riser.code === 'UCL' ? 'Champions League win' : 'title'} probability has
            increased by <b>{pp(riser.after - riser.before).replace('pp', ' pp')}</b> since{' '}
            {riser.fromMd === 0 ? 'pre-season' : `MW ${riser.fromMd}`}.
          </p>
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Recent updates
// ---------------------------------------------------------------------------
function RecentUpdates({ bundles }: { bundles: Bundles }) {
  const latest = movers(bundles, 1)
    .filter((m) => Math.abs(m.after - m.before) >= 0.005)
    .slice(0, 3)
  const synced = [...bundles.values()]
    .map((b) => b.summary.freshness.last_ingested_at)
    .filter((x): x is string => !!x)
    .sort()
    .pop()
  return (
    <Card>
      <CardHeader
        icon={<RefreshIcon />}
        title="Recent Updates"
        subtitle="Latest changes to forecasts and model inputs."
      />
      <ul className="divide-y divide-ink-700/60 text-[13px]">
        {latest.map((m) => {
          const up = m.after >= m.before
          return (
            <li key={`${m.code}-${m.team.id}`} className="flex items-center gap-3 py-2.5">
              {up ? (
                <ArrowUpIcon size={16} className="shrink-0 text-good" aria-label="up" />
              ) : (
                <ArrowDownIcon size={16} className="shrink-0 text-bad" aria-label="down" />
              )}
              <a href={`#/teams/${m.team.id}`} className="w-[92px] shrink-0 truncate font-medium text-white">
                {teamName(m.team)}
              </a>
              <span className={`tabular w-[62px] shrink-0 ${up ? 'text-good' : 'text-bad'}`}>
                {pp(m.after - m.before)}
              </span>
              <span className="min-w-0 flex-1 truncate text-slate-300">
                {m.code === 'EPL' ? 'Title probability' : `${COMPETITION_SHORT[m.code]} ${m.code === 'UCL' ? 'win' : 'title'}`}{' '}
                ({pct(m.before)} → {pct(m.after)})
              </span>
              <span className="shrink-0 text-[11.5px] text-slate-500">{m.toMd === 0 ? 'Pre' : `MW ${m.toMd}`}</span>
            </li>
          )
        })}
        <li className="flex items-center gap-3 py-2.5">
          <span className="ml-1 h-2.5 w-2.5 shrink-0 rounded-full bg-brand-500" />
          <span className="w-[92px] shrink-0 font-medium text-white">Data updated</span>
          <span className="min-w-0 flex-1 truncate text-slate-300">Fixture results and tables synced.</span>
          <span className="shrink-0 text-[11.5px] text-slate-500">{synced ? timeAgo(synced) : '–'}</span>
        </li>
      </ul>
    </Card>
  )
}

// ---------------------------------------------------------------------------
export function OverviewPage() {
  const { data: bundles, error } = useAllCompetitions()
  if (error) return <ErrorNote error={error} />
  if (!bundles)
    return (
      <div className="grid gap-5 xl:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-[260px] rounded-2xl" />
        ))}
      </div>
    )
  const any = COMPETITION_CODES.some((c) => bundles.get(c)?.forecast)
  return (
    <div className="space-y-5">
      {!any && (
        <EmptyNote>
          No forecasts are published yet. Run the forecast and publish it (see docs/api.md), then refresh.
        </EmptyNote>
      )}
      <div className="grid gap-5 xl:grid-cols-[1.08fr_1fr]">
        <Verdict bundles={bundles} />
        <Glance bundles={bundles} />
      </div>
      <div className="grid gap-5 xl:grid-cols-[1fr_1.37fr]">
        <TitleRace bundles={bundles} />
        <TimelineCard bundles={bundles} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-[1.2fr_1fr_1.27fr]">
        <NextFixtures bundles={bundles} />
        <Insights bundles={bundles} />
        <div className="lg:col-span-2 2xl:col-span-1">
          <RecentUpdates bundles={bundles} />
        </div>
      </div>
      <Disclaimer />
    </div>
  )
}
