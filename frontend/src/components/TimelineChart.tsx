import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { percentAxis } from '../lib/axis'
import { OTHER, SERIES } from '../lib/colors'
import { pct, teamName } from '../lib/format'
import type { Timeline, TeamRef } from '../services/api'
import { EmptyNote } from './ui'


const mdLabel = (md: number) => (md === 0 ? 'Pre' : `MW ${md}`)

export interface Series {
  key: string
  label: string
  color: string
  team?: TeamRef
}

/**
 * Title probability over the season. The top `top` clubs at the latest point get a line
 * each (colour fixed by that order for the whole chart); the rest fold into "Others".
 */
export function TimelineChart({
  timeline,
  top = 4,
  height = 230,
  highlightTeam,
}: {
  timeline: Timeline
  top?: number
  height?: number
  highlightTeam?: number
}) {
  const pts = timeline.points
  if (pts.length === 0) return <EmptyNote>No published forecasts yet.</EmptyNote>
  const latest = pts[pts.length - 1].probs
  let ids = Object.keys(latest)
    .sort((a, b) => latest[b] - latest[a])
    .slice(0, top)
  if (highlightTeam && !ids.includes(String(highlightTeam))) ids = [...ids.slice(0, top - 1), String(highlightTeam)]
  const byId = new Map(timeline.teams.map((t) => [String(t.id), t]))
  const series: Series[] = ids.map((id, i) => ({
    key: id,
    label: teamName(byId.get(id)!),
    color: SERIES[i],
    team: byId.get(id),
  }))
  const data = pts.map((p) => {
    const row: Record<string, number | string> = { md: p.matchday, label: mdLabel(p.matchday) }
    let shown = 0
    for (const s of series) {
      row[s.key] = p.probs[s.key] ?? 0
      shown += p.probs[s.key] ?? 0
    }
    row.others = Math.max(0, 1 - shown)
    return row
  })
  const max = Math.max(...data.flatMap((r) => [...series.map((s) => r[s.key] as number), r.others as number]))
  const axis = percentAxis(max)
  const last = data[data.length - 1]
  const all: Series[] = [...series, { key: 'others', label: 'Others', color: OTHER }]

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-stretch">
      <div className="w-full min-w-0 md:flex-1" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="#262046" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              axisLine={{ stroke: '#262046' }}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={18}
            />
            <YAxis
              domain={axis.domain}
              ticks={axis.ticks}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            <Tooltip
              cursor={{ stroke: '#94a3b8', strokeDasharray: '3 3' }}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                const row = payload[0].payload as Record<string, number>
                return (
                  <div className="rounded-lg border border-ink-600 bg-ink-900/95 px-3 py-2 text-[12px] shadow-xl">
                    <p className="mb-1 font-semibold text-white">{String(label).replace('Pre', 'Pre-season')}</p>
                    {all
                      .slice()
                      .sort((a, b) => row[b.key] - row[a.key])
                      .map((s) => (
                        <p key={s.key} className="flex items-center justify-between gap-4 text-slate-300">
                          <span className="flex items-center gap-2">
                            <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                            {s.label}
                          </span>
                          <span className="tabular text-white">{pct(row[s.key])}</span>
                        </p>
                      ))}
                  </div>
                )
              }}
            />
            {all.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={s.key === 'others' ? 1.5 : 2}
                strokeDasharray={s.key === 'others' ? '4 3' : undefined}
                dot={false}
                activeDot={{ r: 4, stroke: '#141127', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="shrink-0 self-center rounded-xl border border-ink-700 bg-ink-900/60 px-4 py-3 md:w-[170px]">
        <p className="mb-2 text-[13px] font-semibold text-white">{mdLabel(last.md as number).replace('Pre', 'Pre-season')}</p>
        <ul className="space-y-1.5">
          {all.map((s) => (
            <li key={s.key} className="flex items-center justify-between gap-3 text-[12.5px]">
              <span className="flex min-w-0 items-center gap-2 text-slate-300">
                <span
                  className="h-1 w-3.5 shrink-0 rounded-full"
                  style={{ background: s.color, opacity: s.key === 'others' ? 0.8 : 1 }}
                />
                <span className="truncate">{s.label}</span>
              </span>
              <span className="tabular text-white">{pct(last[s.key] as number)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
