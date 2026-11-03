import { useState } from 'react'
import { navigate } from '../hooks/useRoute'
import { BarsIcon, CrownIcon, TrendIcon, TrophyIcon } from '../components/icons'
import { TimelineChart } from '../components/TimelineChart'
import {
  Card,
  CardHeader,
  Crest,
  Disclaimer,
  Emblem,
  ErrorNote,
  LoadingRows,
  ProbPill,
  RunMeta,
  Tabs,
  ViewAll,
} from '../components/ui'
import { useCompetition } from '../hooks/useSeasonData'
import { COMPETITION_LABEL, COMPETITION_SHORT, pct, teamName, titleProb } from '../lib/format'
import { COMPETITION_CODES, type CompetitionCode, type SeasonForecast, type StandingsResponse } from '../services/api'

const isCode = (c: string | undefined): c is CompetitionCode => COMPETITION_CODES.includes(c as CompetitionCode)

/** One cell per finishing position; opacity = probability (single-hue sequential). */
function PositionStrip({ probs }: { probs: number[] }) {
  const n = probs.length
  return (
    <div className="flex h-5 gap-[2px]" role="img" aria-label="Finishing position probabilities">
      {probs.map((p, i) => (
        <span
          key={i}
          title={`${i + 1}${i === 0 ? 'st' : i === 1 ? 'nd' : i === 2 ? 'rd' : 'th'}: ${pct(p)}`}
          className="rounded-[2px]"
          style={{
            width: n > 24 ? 4 : 6,
            background: p < 0.0005 ? 'rgba(53,45,94,0.45)' : `rgba(139, 92, 246, ${0.15 + Math.min(1, p / 0.6) * 0.85})`,
          }}
        />
      ))}
    </div>
  )
}

function ForecastTable({ f }: { f: SeasonForecast }) {
  const ucl = f.competition === 'UCL'
  const zones = f.zones.filter((z) => z.key !== 'champion')
  const teams = [...f.teams].sort((a, b) => a.expected_position - b.expected_position)
  return (
    <div className="scroll-thin overflow-x-auto">
      <table className="w-full min-w-[760px] text-[13.5px]">
        <thead>
          <tr className="border-b border-ink-700 text-left text-[12.5px] text-slate-400">
            <th className="py-2 pr-2 font-medium">#</th>
            <th className="py-2 font-medium">Team</th>
            <th className="py-2 pl-3 text-right font-medium">P</th>
            <th className="py-2 pl-3 text-right font-medium">Pts</th>
            <th className="py-2 pl-3 text-right font-medium" title="Expected final points">xPts</th>
            {!ucl && <th className="py-2 pl-3 text-center font-medium">Title</th>}
            {zones.map((z) => (
              <th key={z.key} className="py-2 pl-4 text-right leading-tight font-medium" title={`Positions ${z.first_position}–${z.last_position}`}>
                {z.label}
              </th>
            ))}
            <th className="py-2 pl-5 font-medium whitespace-nowrap">Finishing position (1 → {f.teams.length})</th>
          </tr>
        </thead>
        <tbody>
          {teams.map((t, i) => (
            <tr key={t.team.id} className="border-b border-ink-700/40 last:border-0 hover:bg-ink-800/40">
              <td className="py-2 pr-2 text-slate-400">{i + 1}</td>
              <td className="py-2">
                <a href={`#/teams/${t.team.id}`} className="flex items-center gap-2.5 text-white hover:text-brand-300">
                  <Crest team={t.team} size={22} />
                  <span className="truncate whitespace-nowrap">{teamName(t.team)}</span>
                </a>
              </td>
              <td className="tabular py-2 pl-3 text-right text-slate-400">{t.played}</td>
              <td className="tabular py-2 pl-3 text-right text-white">{t.current_points}</td>
              <td className="tabular py-2 pl-3 text-right text-slate-200">{t.expected_points.toFixed(1)}</td>
              {!ucl && (
                <td className="py-2 pl-3 text-center">
                  <ProbPill p={titleProb(t, f.competition)}>{pct(titleProb(t, f.competition))}</ProbPill>
                </td>
              )}
              {zones.map((z) => (
                <td key={z.key} className="tabular py-2 pl-4 text-right text-slate-200">
                  {pct(t.zone_probs[z.key])}
                </td>
              ))}
              <td className="py-2 pl-5">
                <PositionStrip probs={t.position_probs} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StandingsTable({ s }: { s: StandingsResponse }) {
  const formColor: Record<string, string> = { W: 'bg-good/80', D: 'bg-slate-500', L: 'bg-bad/80' }
  return (
    <div className="scroll-thin overflow-x-auto">
      <table className="w-full min-w-[420px] text-[13px]">
        <thead>
          <tr className="border-b border-ink-700 text-left text-[12px] text-slate-400">
            <th className="py-2 font-medium">#</th>
            <th className="py-2 font-medium">Team</th>
            <th className="py-2 text-right font-medium">P</th>
            <th className="py-2 text-right font-medium">GD</th>
            <th className="py-2 text-right font-medium">Pts</th>
            <th className="py-2 pl-3 font-medium">Form</th>
          </tr>
        </thead>
        <tbody>
          {s.rows.map((r) => (
            <tr key={r.team.id} className="border-b border-ink-700/40 last:border-0">
              <td className="py-1.5 text-slate-400">{r.position}</td>
              <td className="py-1.5">
                <a href={`#/teams/${r.team.id}`} className="flex items-center gap-2 text-white hover:text-brand-300">
                  <Crest team={r.team} size={18} />
                  <span className="truncate">{teamName(r.team)}</span>
                </a>
              </td>
              <td className="tabular py-1.5 text-right text-slate-400">{r.played}</td>
              <td className="tabular py-1.5 text-right text-slate-300">
                {r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}
              </td>
              <td className="tabular py-1.5 text-right font-semibold text-white">{r.points}</td>
              <td className="py-1.5 pl-3">
                <span className="flex gap-1">
                  {r.form.map((x, i) => (
                    <span
                      key={i}
                      className={`inline-flex h-4 w-4 items-center justify-center rounded-[4px] text-[9px] font-bold text-white ${formColor[x]}`}
                    >
                      {x}
                    </span>
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-[11.5px] text-slate-500">{s.ordering_note}</p>
    </div>
  )
}

export function CompetitionsPage({ code: routeCode }: { code?: string }) {
  const code: CompetitionCode = isCode(routeCode) ? routeCode : 'EPL'
  const { data, error } = useCompetition(code)
  const [view, setView] = useState<'forecast' | 'table'>('forecast')

  const tabs = (
    <Tabs
      value={code}
      onChange={(c) => navigate(`/competitions/${c}`)}
      items={COMPETITION_CODES.map((c) => ({ value: c, label: COMPETITION_SHORT[c] }))}
    />
  )
  if (error)
    return (
      <div className="space-y-5">
        {tabs}
        <ErrorNote error={error} />
      </div>
    )
  const f = data?.forecast
  const leader = f && [...f.teams].sort((a, b) => titleProb(b, code) - titleProb(a, code))[0]
  return (
    <div className="space-y-5">
      {tabs}
      <section className="card relative overflow-hidden p-6">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_90%_0%,rgba(139,92,246,0.3),transparent_60%)]" />
        <div className="relative flex flex-wrap items-center gap-5">
          <Emblem url={data?.summary.emblem_url} code={code} size={56} />
          <div className="min-w-0 flex-1">
            <h2 className="text-[24px] font-semibold text-white">{COMPETITION_LABEL[code]}</h2>
            <p className="text-[14px] text-slate-400">
              {data ? `${data.summary.season_label} · ${data.summary.country ?? 'Europe'} · ${f?.teams.length} clubs` : 'Loading…'}
            </p>
          </div>
          {leader && (
            <div className="flex items-center gap-4">
              <Crest team={leader.team} size={44} />
              <div>
                <p className="text-[13px] text-slate-400">{code === 'UCL' ? 'Favourite' : 'Title favourite'}</p>
                <p className="text-[17px] font-semibold text-white">
                  {teamName(leader.team)} <span className="text-brand-300">{pct(titleProb(leader, code))}</span>
                </p>
              </div>
            </div>
          )}
        </div>
        {f && <RunMeta run={f.run} className="relative mt-5 border-t border-ink-700/70 pt-4" />}
      </section>

      <div className="grid gap-5 min-[1800px]:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader
            icon={view === 'forecast' ? <TrophyIcon /> : <BarsIcon />}
            title={view === 'forecast' ? 'Season Forecast' : 'Current Table'}
            subtitle={
              view === 'forecast'
                ? code === 'UCL'
                  ? 'League phase: chance of each finishing zone. Knockouts on the UCL Simulator.'
                  : 'Chance of each outcome, sorted by expected finishing position.'
                : 'Computed from results so far.'
            }
            action={
              <div className="flex items-center gap-3">
                {code === 'UCL' && <ViewAll href="#/ucl" label="Knockouts" />}
                <Tabs
                  value={view}
                  onChange={setView}
                  items={[
                    { value: 'forecast', label: 'Forecast' },
                    { value: 'table', label: 'Table' },
                  ]}
                />
              </div>
            }
          />
          {!data ? (
            <LoadingRows rows={10} />
          ) : view === 'forecast' ? (
            <ForecastTable f={data.forecast} />
          ) : data.standings ? (
            <StandingsTable s={data.standings} />
          ) : (
            <LoadingRows rows={10} />
          )}
        </Card>
        <div className="space-y-5">
          <Card>
            <CardHeader
              icon={<TrendIcon />}
              title={code === 'UCL' ? 'Win Probability Timeline' : 'Title Probability Timeline'}
              subtitle="Matchday by matchday this season."
            />
            {data?.timeline ? <TimelineChart timeline={data.timeline} height={240} /> : <LoadingRows rows={5} />}
          </Card>
          {f && f.zones.length > 0 && (
            <Card>
              <CardHeader icon={<CrownIcon />} title="Zones" subtitle="From this season’s competition rules." />
              <ul className="space-y-2 text-[13px]">
                {f.zones.map((z) => (
                  <li key={z.key} className="flex justify-between gap-3 text-slate-300">
                    <span>{z.label}</span>
                    <span className="tabular text-slate-400">
                      {z.first_position === z.last_position
                        ? `${z.first_position}`
                        : `${z.first_position}–${z.last_position}`}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
      <Disclaimer />
    </div>
  )
}
