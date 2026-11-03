import type { ReactNode } from 'react'
import { AlertIcon, CheckIcon, DatabaseIcon, RefreshIcon } from '../components/icons'
import { Card, CardHeader, Disclaimer, Emblem, ErrorNote, LoadingRows, Meter } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { COMPETITION_SHORT, fmtDateTime, timeAgo } from '../lib/format'
import { api, type CompetitionCode } from '../services/api'

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { cls: string; icon: ReactNode; label: string }> = {
    succeeded: { cls: 'text-good bg-good/10 border-good/30', icon: <CheckIcon size={13} />, label: 'Succeeded' },
    partial: { cls: 'text-warn bg-warn/10 border-warn/30', icon: <AlertIcon size={13} />, label: 'Partial' },
    failed: { cls: 'text-bad bg-bad/10 border-bad/30', icon: <AlertIcon size={13} />, label: 'Failed' },
    running: { cls: 'text-slate-300 bg-ink-800 border-ink-600', icon: <RefreshIcon size={13} />, label: 'Running' },
  }
  const s = map[status] ?? map.running
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] ${s.cls}`}>
      {s.icon}
      {s.label}
    </span>
  )
}

const SOURCES = [
  { label: 'Fixtures, results & squads', value: 'football-data.org (free tier), 2023/24 onwards' },
  { label: 'Competition rules', value: 'Official handbooks (Premier League, DFL, UEFA); La Liga & Serie A from verified secondary sources' },
  { label: 'Tables', value: 'Computed from results; the provider’s table is only used as a cross-check' },
  { label: 'Times', value: 'Stored in UTC, shown in your local time' },
]

export function DataCentrePage() {
  const status = useApi(() => api.dataStatus(), [])
  const comps = useApi(() => api.competitions(), [])
  if (status.error) return <ErrorNote error={status.error} />
  if (!status.data) return <LoadingRows rows={10} />
  const emblems = new Map((comps.data ?? []).map((c) => [c.code, c.emblem_url] as [CompetitionCode, string | null]))
  const d = status.data

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-5">
        {d.competitions.map((c) => {
          const fresh = c.freshness
          return (
            <section key={c.code} className="card p-4">
              <div className="flex items-center gap-2.5">
                <Emblem url={emblems.get(c.code)} code={c.code} size={28} />
                <span className="flex-1 text-[14px] font-semibold text-white">{COMPETITION_SHORT[c.code]}</span>
                {fresh.is_stale ? (
                  <span className="flex items-center gap-1 text-[11.5px] text-warn">
                    <AlertIcon size={13} /> Stale
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[11.5px] text-good">
                    <CheckIcon size={13} /> Fresh
                  </span>
                )}
              </div>
              <div className="mt-4 mb-1.5 flex justify-between text-[12.5px] text-slate-400">
                <span>Matches played</span>
                <span className="tabular text-white">
                  {c.fixtures_played} / {c.fixtures_total}
                </span>
              </div>
              <Meter value={c.fixtures_total ? c.fixtures_played / c.fixtures_total : 0} />
              <dl className="mt-4 space-y-1.5 text-[12.5px]">
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-400">Last import</dt>
                  <dd className="text-right text-slate-200" title={fresh.last_ingested_at ? fmtDateTime(fresh.last_ingested_at) : ''}>
                    {fresh.last_ingested_at ? timeAgo(fresh.last_ingested_at) : 'never'}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-400">Forecast data cutoff</dt>
                  <dd className="text-right text-slate-200">
                    {c.latest_run_cutoff ? timeAgo(c.latest_run_cutoff) : '–'}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-400">Published forecasts</dt>
                  <dd className="tabular text-right text-slate-200">
                    {c.runs_published} of {c.runs_total}
                  </dd>
                </div>
              </dl>
            </section>
          )
        })}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader icon={<RefreshIcon />} title="Import Log" subtitle="Latest data imports from the provider." />
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead>
                <tr className="border-b border-ink-700 text-left text-[12px] text-slate-400">
                  <th className="py-2 font-medium">When</th>
                  <th className="py-2 font-medium">Competition</th>
                  <th className="py-2 font-medium">Status</th>
                  <th className="py-2 text-right font-medium">New</th>
                  <th className="py-2 text-right font-medium">Updated</th>
                  <th className="py-2 text-right font-medium">Skipped</th>
                  <th className="py-2 text-right font-medium" title="Our table vs the provider's">Table check</th>
                </tr>
              </thead>
              <tbody>
                {d.recent_ingestions.map((r) => (
                  <tr key={r.id} className="border-b border-ink-700/40 last:border-0" title={r.error ?? ''}>
                    <td className="py-2 text-slate-300">{fmtDateTime(r.started_at)}</td>
                    <td className="py-2 text-white">
                      {r.competition ? COMPETITION_SHORT[r.competition] : '–'}
                      {r.season ? <span className="ml-1.5 text-slate-500">{r.season}/{String((r.season + 1) % 100).padStart(2, '0')}</span> : null}
                    </td>
                    <td className="py-2">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="tabular py-2 text-right text-slate-300">{r.fixtures_inserted}</td>
                    <td className="tabular py-2 text-right text-slate-300">{r.fixtures_updated}</td>
                    <td className="tabular py-2 text-right text-slate-300">{r.issues}</td>
                    <td className="py-2 text-right">
                      {r.consistency_ok == null ? (
                        <span className="text-slate-500">–</span>
                      ) : r.consistency_ok ? (
                        <span className="inline-flex items-center gap-1 text-good">
                          <CheckIcon size={13} /> Match
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-warn">
                          <AlertIcon size={13} /> Differs
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card className="self-start">
          <CardHeader icon={<DatabaseIcon />} title="Sources & Rules" />
          <dl className="space-y-3.5 text-[13px]">
            {SOURCES.map((s) => (
              <div key={s.label}>
                <dt className="font-medium text-white">{s.label}</dt>
                <dd className="text-slate-400">{s.value}</dd>
              </div>
            ))}
            <div>
              <dt className="font-medium text-white">Freshness</dt>
              <dd className="text-slate-400">
                Data counts as stale {d.competitions[0]?.freshness.stale_after_hours ?? 48} hours after the last import.
              </dd>
            </div>
          </dl>
        </Card>
      </div>
      <Disclaimer />
    </div>
  )
}
