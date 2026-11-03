import { useEffect, useMemo, useState } from 'react'
import { navigate } from '../hooks/useRoute'
import { CalendarIcon, TargetIcon } from '../components/icons'
import { OTHER, SERIES } from '../lib/colors'
import {
  Card,
  CardHeader,
  Crest,
  Disclaimer,
  Emblem,
  EmptyNote,
  ErrorNote,
  LoadingRows,
  Tabs,
} from '../components/ui'
import { useApi } from '../hooks/useApi'
import { COMPETITION_LABEL, COMPETITION_SHORT, fmtDate, fmtDateTime, fmtTime, pct, STAGE_LABEL, teamName } from '../lib/format'
import { api, COMPETITION_CODES, type CompetitionCode, type Fixture, type FixtureDetail } from '../services/api'

type Filter = 'ALL' | CompetitionCode

/** Home / draw / away as one bar with 2px gaps; every segment is also labelled in text. */
export function OutcomeBar({ f, compact = false }: { f: NonNullable<Fixture['forecast']>; compact?: boolean }) {
  const parts = [
    { key: 'home', p: f.p_home, color: SERIES[0] },
    { key: 'draw', p: f.p_draw, color: OTHER },
    { key: 'away', p: f.p_away, color: SERIES[1] },
  ]
  return (
    <div className={`flex w-full gap-[2px] overflow-hidden rounded-full ${compact ? 'h-1.5' : 'h-3'}`}>
      {parts.map((x) => (
        <span key={x.key} style={{ width: `${x.p * 100}%`, background: x.color }} title={`${x.key}: ${pct(x.p)}`} />
      ))}
    </div>
  )
}

function FixtureList({
  fixtures,
  selected,
  emblems,
}: {
  fixtures: Fixture[]
  selected?: number
  emblems: Map<CompetitionCode, string | null>
}) {
  let lastDay = ''
  return (
    <ul className="scroll-thin max-h-[720px] overflow-y-auto pr-1">
      {fixtures.map((f) => {
        const day = f.kickoff_utc ? fmtDate(f.kickoff_utc) : 'TBC'
        const header = day !== lastDay
        lastDay = day
        return (
          <li key={f.id}>
            {header && <p className="sticky top-0 bg-ink-850 pt-3 pb-1.5 text-[12px] font-medium text-slate-400">{day}</p>}
            <button
              type="button"
              onClick={() => navigate(`/match-predictor/${f.id}`)}
              className={`mb-1.5 w-full rounded-xl border px-3 py-2.5 text-left transition-colors ${
                f.id === selected ? 'border-brand-500 bg-brand-600/15' : 'border-ink-700 bg-ink-800/40 hover:border-ink-600'
              }`}
            >
              <div className="flex items-center gap-2 text-[13.5px]">
                <Emblem url={emblems.get(f.competition)} code={f.competition} size={20} />
                <Crest team={f.home} size={20} />
                <span className="min-w-0 flex-1 truncate text-white">{teamName(f.home)}</span>
                <span className="tabular text-[12px] text-slate-400">{f.kickoff_utc ? fmtTime(f.kickoff_utc) : ''}</span>
                <span className="min-w-0 flex-1 truncate text-right text-white">{teamName(f.away)}</span>
                <Crest team={f.away} size={20} />
              </div>
              {f.forecast && (
                <div className="mt-2 flex items-center gap-2 text-[11.5px] text-slate-400">
                  <span className="tabular w-10">{pct(f.forecast.p_home, 0)}</span>
                  <OutcomeBar f={f.forecast} compact />
                  <span className="tabular w-10 text-right">{pct(f.forecast.p_away, 0)}</span>
                </div>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function ScoreGrid({ d }: { d: FixtureDetail }) {
  const m = d.score_matrix!
  const max = Math.max(...m.flat())
  return (
    <div>
      <div className="grid grid-cols-[auto_repeat(6,minmax(0,1fr))] gap-[3px] text-[11.5px]">
        <span className="flex items-end justify-center pb-1 text-[10px] text-slate-500">
          {d.home.tla ?? 'H'}↓ {d.away.tla ?? 'A'}→
        </span>
        {m[0].map((_, j) => (
          <span key={j} className="pb-1 text-center text-slate-400">
            {j}
          </span>
        ))}
        {m.map((row, i) => (
          <div key={i} className="contents">
            <span className="flex items-center pr-2 text-slate-400">{i}</span>
            {row.map((p, j) => (
              <span
                key={j}
                title={`${teamName(d.home)} ${i}–${j} ${teamName(d.away)}: ${pct(p)}`}
                className="tabular flex aspect-[1.6] items-center justify-center rounded-[4px] text-white"
                style={{ background: `rgba(139, 92, 246, ${0.08 + (p / max) * 0.8})` }}
              >
                {p >= 0.01 ? `${Math.round(p * 100)}` : ''}
              </span>
            ))}
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] text-slate-500">
        Rows: {teamName(d.home)} goals · columns: {teamName(d.away)} goals · cells in % (blank &lt; 1%).
      </p>
    </div>
  )
}

function Detail({ id }: { id: number }) {
  const { data: d, error } = useApi(() => api.fixture(id), [id])
  if (error) return <ErrorNote error={error} />
  if (!d) return <LoadingRows rows={8} />
  const fc = d.forecast
  const played = d.home_score != null
  return (
    <div className="space-y-5">
      <section className="card relative overflow-hidden p-6">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(139,92,246,0.3),transparent_60%)]" />
        <p className="relative text-center text-[13px] text-slate-400">
          {COMPETITION_LABEL[d.competition]} · {STAGE_LABEL[d.stage] ?? d.stage}
          {d.matchday ? ` · Matchday ${d.matchday}` : ''}
        </p>
        <div className="relative mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <a href={`#/teams/${d.home.id}`} className="flex flex-col items-center gap-2 text-center">
            <Crest team={d.home} size={64} />
            <span className="text-[17px] font-semibold text-white">{teamName(d.home)}</span>
            <span className="text-[12px] text-slate-500">Home</span>
          </a>
          <div className="text-center">
            {played ? (
              <p className="tabular text-[40px] font-bold text-white">
                {d.home_score} – {d.away_score}
              </p>
            ) : (
              <p className="text-[22px] font-semibold text-slate-300">vs</p>
            )}
            {d.kickoff_utc && <p className="mt-1 text-[13px] text-slate-400">{fmtDateTime(d.kickoff_utc)}</p>}
          </div>
          <a href={`#/teams/${d.away.id}`} className="flex flex-col items-center gap-2 text-center">
            <Crest team={d.away} size={64} />
            <span className="text-[17px] font-semibold text-white">{teamName(d.away)}</span>
            <span className="text-[12px] text-slate-500">Away</span>
          </a>
        </div>
        {fc ? (
          <div className="relative mt-6">
            <div className="mb-2 grid grid-cols-3 text-[13px]">
              <span className="text-slate-300">
                Home win <b className="tabular ml-1 text-[18px] text-white">{pct(fc.p_home)}</b>
              </span>
              <span className="text-center text-slate-300">
                Draw <b className="tabular ml-1 text-[18px] text-white">{pct(fc.p_draw)}</b>
              </span>
              <span className="text-right text-slate-300">
                Away win <b className="tabular ml-1 text-[18px] text-white">{pct(fc.p_away)}</b>
              </span>
            </div>
            <OutcomeBar f={fc} />
            <div className="mt-4 flex justify-center gap-8 text-[13px] text-slate-400">
              <span>
                Expected goals <b className="tabular text-white">{fc.xg_home.toFixed(2)}</b> –{' '}
                <b className="tabular text-white">{fc.xg_away.toFixed(2)}</b>
              </span>
            </div>
            <p className="mt-3 text-center text-[11.5px] text-slate-500">
              Model v{fc.model_version} · data cutoff {fmtDateTime(fc.data_cutoff)} · probabilities for 90 minutes
            </p>
          </div>
        ) : (
          <div className="relative mt-6">
            <EmptyNote>
              {played
                ? 'This match has been played; forecasts are only shown before kickoff.'
                : 'No published forecast covers this fixture yet.'}
            </EmptyNote>
          </div>
        )}
      </section>
      {fc && d.score_matrix && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader title="Most Likely Scorelines" subtitle="Exact score after 90 minutes." />
            <ul className="space-y-2">
              {d.likely_scorelines.slice(0, 8).map((s) => {
                const top = d.likely_scorelines[0].probability
                return (
                  <li key={`${s.home}-${s.away}`} className="flex items-center gap-3 text-[13.5px]">
                    <span className="tabular w-12 font-semibold text-white">
                      {s.home}–{s.away}
                    </span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-ink-700">
                      <span
                        className="block h-full rounded-full bg-brand-500"
                        style={{ width: `${(s.probability / top) * 100}%` }}
                      />
                    </span>
                    <span className="tabular w-12 text-right text-slate-300">{pct(s.probability)}</span>
                  </li>
                )
              })}
            </ul>
          </Card>
          <Card>
            <CardHeader title="Score Grid" subtitle="Chance of every scoreline up to 5–5." />
            <ScoreGrid d={d} />
          </Card>
        </div>
      )}
    </div>
  )
}

export function MatchPredictorPage({ fixtureId }: { fixtureId?: number }) {
  const [filter, setFilter] = useState<Filter>('ALL')
  const upcoming = useApi(() => api.upcoming(14), [])
  const comps = useApi(() => api.competitions(), [])
  const emblems = useMemo(
    () => new Map((comps.data ?? []).map((c) => [c.code, c.emblem_url] as [CompetitionCode, string | null])),
    [comps.data],
  )
  const list = (upcoming.data ?? []).filter((f) => filter === 'ALL' || f.competition === filter)
  const selected = fixtureId ?? list[0]?.id

  useEffect(() => {
    // Open the first fixture when arriving without one.
    if (!fixtureId && list[0]) navigate(`/match-predictor/${list[0].id}`)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upcoming.data])

  const changeFilter = (v: Filter) => {
    setFilter(v)
    const first = (upcoming.data ?? []).find((f) => v === 'ALL' || f.competition === v)
    if (first) navigate(`/match-predictor/${first.id}`)
  }

  return (
    <div className="space-y-5">
      <Tabs
        value={filter}
        onChange={changeFilter}
        items={[
          { value: 'ALL' as Filter, label: 'All' },
          ...COMPETITION_CODES.map((c) => ({ value: c as Filter, label: COMPETITION_SHORT[c] })),
        ]}
      />
      <div className="grid gap-5 xl:grid-cols-[400px_1fr]">
        <Card className="self-start">
          <CardHeader icon={<CalendarIcon />} title="Upcoming Fixtures" subtitle="Next 14 days · local time" />
          {upcoming.error ? (
            <ErrorNote error={upcoming.error} />
          ) : !upcoming.data ? (
            <LoadingRows rows={8} />
          ) : list.length === 0 ? (
            <EmptyNote>No fixtures in the next 14 days.</EmptyNote>
          ) : (
            <FixtureList fixtures={list} selected={selected} emblems={emblems} />
          )}
        </Card>
        <div>
          {selected ? (
            <Detail id={selected} />
          ) : (
            <Card>
              <CardHeader icon={<TargetIcon />} title="Pick a fixture" />
              <EmptyNote>Select a match on the left to see its forecast.</EmptyNote>
            </Card>
          )}
        </div>
      </div>
      <Disclaimer />
    </div>
  )
}
