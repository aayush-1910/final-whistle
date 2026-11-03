import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CalendarIcon, ShieldIcon, TrendIcon, TrophyIcon } from '../components/icons'
import {
  Card,
  CardHeader,
  Crest,
  Disclaimer,
  Emblem,
  EmptyNote,
  ErrorNote,
  LoadingRows,
  RunMeta,
  Tabs,
} from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAllCompetitions, type CompetitionBundle } from '../hooks/useSeasonData'
import { percentAxis } from '../lib/axis'
import { COMPETITION_SHORT, fmtDate, fmtTime, pct, teamName, titleProb } from '../lib/format'
import { api, COMPETITION_CODES, type CompetitionCode, type Fixture } from '../services/api'
import { OutcomeBar } from './MatchPredictor'

type Bundles = Map<CompetitionCode, CompetitionBundle>

function TeamPicker({ bundles }: { bundles: Bundles }) {
  const [code, setCode] = useState<CompetitionCode>('EPL')
  const f = bundles.get(code)?.forecast
  const teams = f ? [...f.teams].sort((a, b) => teamName(a.team).localeCompare(teamName(b.team))) : []
  return (
    <Card>
      <CardHeader
        icon={<ShieldIcon />}
        title="Choose a club"
        subtitle="Or search any club with Ctrl K."
        action={
          <Tabs value={code} onChange={setCode} items={COMPETITION_CODES.map((c) => ({ value: c, label: COMPETITION_SHORT[c] }))} />
        }
      />
      {!f ? (
        <EmptyNote>No published forecast for this competition yet.</EmptyNote>
      ) : (
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          {teams.map((t) => (
            <a
              key={t.team.id}
              href={`#/teams/${t.team.id}`}
              className="flex items-center gap-3 rounded-xl border border-ink-700 bg-ink-800/40 px-3 py-3 hover:border-brand-500/60"
            >
              <Crest team={t.team} size={30} />
              <span className="min-w-0">
                <span className="block truncate text-[14px] text-white">{teamName(t.team)}</span>
                <span className="tabular block text-[12px] text-slate-400">
                  {code === 'UCL' ? 'Win' : 'Title'} {pct(titleProb(t, code))}
                </span>
              </span>
            </a>
          ))}
        </div>
      )}
    </Card>
  )
}

function FixtureRow({ f, teamId }: { f: Fixture; teamId: number }) {
  const home = f.home.id === teamId
  const opp = home ? f.away : f.home
  const played = f.home_score != null
  let res: 'W' | 'D' | 'L' | null = null
  if (played) {
    const gf = home ? f.home_score! : f.away_score!
    const ga = home ? f.away_score! : f.home_score!
    const pf = home ? f.home_penalties : f.away_penalties
    const pa = home ? f.away_penalties : f.home_penalties
    res = gf > ga ? 'W' : gf < ga ? 'L' : pf != null && pa != null ? (pf > pa ? 'W' : 'L') : 'D'
  }
  const resColor = { W: 'bg-good/80', D: 'bg-slate-500', L: 'bg-bad/80' }
  return (
    <a href={`#/match-predictor/${f.id}`} className="flex items-center gap-3 py-2.5 text-[13.5px] hover:bg-ink-800/40">
      <span className="w-[86px] shrink-0 text-[12px] text-slate-400">
        {f.kickoff_utc ? fmtDate(f.kickoff_utc) : 'TBC'}
        {!played && f.kickoff_utc && <span className="block">{fmtTime(f.kickoff_utc)}</span>}
      </span>
      <span className="w-6 shrink-0 text-[11px] text-slate-500">{home ? 'H' : 'A'}</span>
      <Crest team={opp} size={22} />
      <span className="min-w-0 flex-1 truncate text-white">{teamName(opp)}</span>
      <span className="hidden text-[11.5px] text-slate-500 sm:inline">{COMPETITION_SHORT[f.competition]}</span>
      {played ? (
        <span className="flex items-center gap-2">
          <span className="tabular text-white">
            {f.home_score}–{f.away_score}
          </span>
          <span className={`inline-flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold text-white ${resColor[res!]}`}>
            {res}
          </span>
        </span>
      ) : f.forecast ? (
        <span className="w-[120px]">
          <span className="mb-1 flex justify-between text-[11px] text-slate-400">
            <span className="tabular">W {pct(home ? f.forecast.p_home : f.forecast.p_away, 0)}</span>
            <span className="tabular">D {pct(f.forecast.p_draw, 0)}</span>
          </span>
          <OutcomeBar f={f.forecast} compact />
        </span>
      ) : null}
    </a>
  )
}

function CompetitionOutlook({ code, bundle, teamId }: { code: CompetitionCode; bundle: CompetitionBundle; teamId: number }) {
  const f = bundle.forecast!
  const t = f.teams.find((x) => x.team.id === teamId)
  if (!t) return null
  const zones = f.zones.filter((z) => z.key !== 'champion')
  const tl = bundle.timeline
  const series =
    tl?.points.map((p) => ({
      label: p.matchday === 0 ? 'Pre' : `MW ${p.matchday}`,
      p: p.probs[String(teamId)] ?? 0,
      xpts: p.expected_points[String(teamId)],
    })) ?? []
  const metric = code === 'UCL' ? 'Win probability' : 'Title probability'
  const maxP = Math.max(0.04, ...series.map((s) => s.p))
  return (
    <Card>
      <CardHeader
        icon={<Emblem url={bundle.summary.emblem_url} code={code} size={26} />}
        title={COMPETITION_SHORT[code]}
        subtitle={`${f.season_label} · ${t.played} played · ${t.current_points} pts`}
        action={
          <a href={code === 'UCL' ? '#/ucl' : `#/competitions/${code}`} className="text-[13px] text-brand-400 hover:text-brand-300">
            Full table →
          </a>
        }
      />
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          { label: metric, value: pct(titleProb(t, code)) },
          { label: 'Expected points', value: t.expected_points.toFixed(1) },
          { label: 'Expected position', value: t.expected_position.toFixed(1) },
          ...(code === 'UCL'
            ? [{ label: 'Reach the final', value: pct(t.round_probs?.final) }]
            : [{ label: 'Most likely finish', value: `${t.position_probs.indexOf(Math.max(...t.position_probs)) + 1}` }]),
        ].map((x) => (
          <div key={x.label} className="rounded-xl border border-ink-700 bg-ink-800/50 px-3 py-3">
            <p className="tabular text-[20px] font-semibold text-white">{x.value}</p>
            <p className="text-[12px] text-slate-400">{x.label}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-slate-300">
        {zones.map((z) => (
          <span key={z.key}>
            {z.label} <b className="tabular text-white">{pct(t.zone_probs[z.key])}</b>
          </span>
        ))}
      </div>
      {series.length > 1 && (
        <div className="mt-5">
          <p className="mb-2 flex items-center gap-2 text-[13px] text-slate-400">
            <TrendIcon size={16} /> {metric} through the season
          </p>
          <div className="h-[170px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 6, right: 10, bottom: 0, left: -8 }}>
                <CartesianGrid stroke="#262046" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={{ stroke: '#262046' }} tickLine={false} minTickGap={16} />
                <YAxis
                  domain={percentAxis(maxP).domain}
                  ticks={percentAxis(maxP).ticks}
                  tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={44}
                />
                <Tooltip
                  cursor={{ stroke: '#94a3b8', strokeDasharray: '3 3' }}
                  content={({ active, payload, label }) =>
                    active && payload?.length ? (
                      <div className="rounded-lg border border-ink-600 bg-ink-900/95 px-3 py-2 text-[12px] shadow-xl">
                        <p className="font-semibold text-white">{label === 'Pre' ? 'Pre-season' : label}</p>
                        <p className="text-slate-300">
                          {metric}: <span className="tabular text-white">{pct(payload[0].payload.p)}</span>
                        </p>
                        <p className="text-slate-300">
                          Expected points: <span className="tabular text-white">{payload[0].payload.xpts?.toFixed(1)}</span>
                        </p>
                      </div>
                    ) : null
                  }
                />
                <Line type="monotone" dataKey="p" stroke="#8b5cf6" strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: '#141127', strokeWidth: 2 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      <RunMeta run={f.run} className="mt-4 border-t border-ink-700/70 pt-3" />
    </Card>
  )
}

function TeamView({ teamId, bundles }: { teamId: number; bundles: Bundles }) {
  const { data: t, error } = useApi(() => api.team(teamId), [teamId])
  if (error) return <ErrorNote error={error} />
  if (!t) return <LoadingRows rows={8} />
  const current = COMPETITION_CODES.filter((c) => bundles.get(c)?.forecast?.teams.some((x) => x.team.id === teamId))
  const pastSeasons = t.seasons.filter((s) => !(current.includes(s.competition) && s.season === bundles.get(s.competition)?.summary.current_season))
  return (
    <div className="space-y-5">
      <section className="card relative overflow-hidden p-6">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_90%_0%,rgba(139,92,246,0.35),transparent_60%)]" />
        <div className="relative flex flex-wrap items-center gap-5">
          <Crest team={t.team} size={84} />
          <div>
            <h2 className="text-[28px] font-bold text-white">{t.team.name}</h2>
            <p className="text-[14px] text-slate-400">
              {t.country ?? ''}
              {current.length ? ` · ${current.map((c) => COMPETITION_SHORT[c]).join(' · ')}` : ''}
            </p>
          </div>
          <a href="#/teams" className="ml-auto text-[13px] text-brand-400 hover:text-brand-300">
            ← All clubs
          </a>
        </div>
      </section>
      <div className="grid gap-5 2xl:grid-cols-2">
        {current.map((c) => (
          <CompetitionOutlook key={c} code={c} bundle={bundles.get(c)!} teamId={teamId} />
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader icon={<CalendarIcon />} title="Next Fixtures" subtitle="With the model’s win / draw chances." />
          {t.upcoming_fixtures.length ? (
            <div className="divide-y divide-ink-700/60">
              {t.upcoming_fixtures.map((f) => (
                <FixtureRow key={f.id} f={f} teamId={teamId} />
              ))}
            </div>
          ) : (
            <EmptyNote>No upcoming fixtures scheduled.</EmptyNote>
          )}
        </Card>
        <Card>
          <CardHeader icon={<TrophyIcon />} title="Recent Results" subtitle="Last five matches, all competitions." />
          {t.recent_results.length ? (
            <div className="divide-y divide-ink-700/60">
              {t.recent_results.map((f) => (
                <FixtureRow key={f.id} f={f} teamId={teamId} />
              ))}
            </div>
          ) : (
            <EmptyNote>No results yet.</EmptyNote>
          )}
        </Card>
      </div>
      {pastSeasons.length > 0 && (
        <Card>
          <CardHeader title="Previous Seasons" subtitle="Final league positions computed from results." />
          <div className="flex flex-wrap gap-2.5">
            {pastSeasons.map((s) => (
              <span key={`${s.competition}-${s.season}`} className="rounded-xl border border-ink-700 bg-ink-800/50 px-3 py-2 text-[13px] text-slate-300">
                {COMPETITION_SHORT[s.competition]} {s.season}/{String((s.season + 1) % 100).padStart(2, '0')}
                {s.competition !== 'UCL' && s.position ? (
                  <b className="ml-2 text-white">
                    {s.position}
                    {s.position === 1 ? 'st' : s.position === 2 ? 'nd' : s.position === 3 ? 'rd' : 'th'}
                  </b>
                ) : null}
                <span className="ml-2 text-slate-500">{s.points} pts</span>
              </span>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

export function TeamExplorerPage({ teamId }: { teamId?: number }) {
  const { data: bundles, error } = useAllCompetitions()
  if (error) return <ErrorNote error={error} />
  if (!bundles) return <LoadingRows rows={8} />
  return (
    <div className="space-y-5">
      {teamId ? <TeamView teamId={teamId} bundles={bundles} /> : <TeamPicker bundles={bundles} />}
      <Disclaimer />
    </div>
  )
}
