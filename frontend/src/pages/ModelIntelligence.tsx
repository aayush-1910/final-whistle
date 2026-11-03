import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { BarsIcon, CheckIcon, InfoIcon, TargetIcon, TrendIcon } from '../components/icons'
import { Card, CardHeader, Disclaimer, EmptyNote, ErrorNote, LoadingRows } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { COMPETITION_SHORT, fmtDate, pct } from '../lib/format'
import { api, type CompetitionCode } from '../services/api'

type ModelMetrics = Record<string, { n: number; log_loss: number; brier: number; rps: number; accuracy: number; ece: number }>
type CalBin = { lower: number; upper: number; count: number; mean_predicted: number; observed_rate: number }
type SeasonMetrics = Record<string, Record<string, number>>

const PROD = 'Poisson (tuned)'
const MODEL_ORDER = ['Poisson (tuned)', 'Poisson (default)', 'Blend (tuned)', 'Elo (tuned)', 'Elo (default)', 'base rates']
const MODEL_LABEL: Record<string, string> = {
  'Poisson (tuned)': 'Poisson (production)',
  'Poisson (default)': 'Poisson (default settings)',
  'Blend (tuned)': 'Elo + Poisson blend',
  'Elo (tuned)': 'Elo (tuned)',
  'Elo (default)': 'Elo (default)',
  'base rates': 'League averages (baseline)',
}

const STEPS = [
  {
    title: 'Rate every team',
    body: 'A Poisson goals model estimates each club’s attacking and defensive strength from results in all five competitions since 2023, weighting recent matches more (half-life about a year).',
  },
  {
    title: 'Price every match',
    body: 'Expected goals for both sides give the chance of every scoreline, and so of a home win, draw or away win.',
  },
  {
    title: 'Play the season 10,000 times',
    body: 'Every remaining fixture is simulated, with uncertainty in team strength, and each simulated table is ranked with the competition’s real tiebreak rules.',
  },
  {
    title: 'Count the outcomes',
    body: 'If a club wins the title in 2,460 of 10,000 seasons, its title probability is 24.6%.',
  },
]

function CalibrationChart({ bins }: { bins: CalBin[] }) {
  const data = bins.filter((b) => b.count > 0).map((b) => ({ x: b.mean_predicted, y: b.observed_rate, n: b.count }))
  return (
    <div className="h-[260px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 18, left: -4 }}>
          <CartesianGrid stroke="#262046" strokeDasharray="2 4" />
          <XAxis
            type="number"
            dataKey="x"
            domain={[0, 1]}
            ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
            tickFormatter={(v: number) => `${v * 100}%`}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            axisLine={{ stroke: '#262046' }}
            tickLine={false}
            label={{ value: 'Predicted probability', position: 'insideBottom', offset: -10, fill: '#94a3b8', fontSize: 12 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            domain={[0, 1]}
            ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
            tickFormatter={(v: number) => `${v * 100}%`}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <Tooltip
            cursor={false}
            content={({ active, payload }) => {
              const d = payload?.[0]?.payload as { x: number; y: number; n: number } | undefined
              if (!active || !d || d.n === undefined) return null
              return (
                <div className="rounded-lg border border-ink-600 bg-ink-900/95 px-3 py-2 text-[12px] shadow-xl">
                  <p className="text-slate-300">
                    Predicted <span className="tabular text-white">{pct(d.x)}</span>
                  </p>
                  <p className="text-slate-300">
                    Happened <span className="tabular text-white">{pct(d.y)}</span>
                  </p>
                  <p className="text-slate-500">{d.n.toLocaleString()} outcomes</p>
                </div>
              )
            }}
          />
          <Line
            data={[
              { x: 0, y: 0 },
              { x: 1, y: 1 },
            ]}
            dataKey="y"
            stroke="#6b6688"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            dot={false}
            activeDot={false}
            isAnimationActive={false}
            legendType="none"
          />
          <Scatter dataKey="y" fill="#8b5cf6" stroke="#141127" strokeWidth={2} isAnimationActive={false} shape="circle" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ModelIntelligencePage() {
  const perf = useApi(() => api.performance(), [])
  const versions = useApi(() => api.modelVersions(), [])
  if (perf.error) return <ErrorNote error={perf.error} />
  if (!perf.data) return <LoadingRows rows={10} />

  const match = perf.data.match_level
  const season = perf.data.season_level
  const overall = (match?.metrics.overall ?? {}) as ModelMetrics
  const calibration = (match?.metrics.calibration ?? []) as CalBin[]
  const byComp = (match?.metrics.by_competition ?? {}) as Record<string, Record<string, number>>
  const prod = overall[PROD]
  const base = overall['base rates']
  const sd = String((season?.params as { chosen_strength_sd?: number })?.chosen_strength_sd ?? '0.15')
  const seasonTest = (season?.metrics.test ?? {}) as SeasonMetrics
  const seasonRow = seasonTest[sd] ?? Object.values(seasonTest)[0]
  const testWindow = match?.test_window as { start?: string; end?: string } | undefined
  const current = versions.data?.find((v) => v.is_current)

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        <section className="card relative overflow-hidden p-6">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_85%_10%,rgba(139,92,246,0.4),transparent_55%)]" />
          <div className="relative">
            <p className="text-[13px] font-semibold tracking-wide text-brand-300">CURRENT MODEL</p>
            <h2 className="mt-2 text-[28px] font-bold text-white">
              Poisson Monte Carlo <span className="text-brand-300">v{perf.data.current_model_version}</span>
            </h2>
            <p className="mt-2 max-w-[520px] text-[14px] text-slate-300">
              Chosen by testing on matches the model had never seen: tuned on 2024/25, then judged once on
              {testWindow?.start ? ` ${fmtDate(testWindow.start)} – ${testWindow.end ? fmtDate(testWindow.end) : 'now'}` : ' later seasons'}.
            </p>
            {prod && base && (
              <div className="mt-6 grid grid-cols-3 gap-3">
                {[
                  { v: pct(prod.accuracy), l: 'Results called correctly', h: `League averages: ${pct(base.accuracy)}` },
                  { v: prod.brier.toFixed(3), l: 'Brier score', h: `League averages: ${base.brier.toFixed(3)} (lower is better)` },
                  { v: pct(prod.ece), l: 'Calibration error', h: 'Average gap between predicted and observed frequency' },
                ].map((x) => (
                  <div key={x.l} className="rounded-xl border border-ink-700 bg-ink-800/60 px-3 py-3" title={x.h}>
                    <p className="tabular text-[22px] font-semibold text-white">{x.v}</p>
                    <p className="text-[12px] text-slate-400">{x.l}</p>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-4 text-[12px] text-slate-500">
              {match ? `${(match.metrics.n_test as number).toLocaleString()} test matches. ` : ''}
              {current ? `${current.published_runs} published forecasts with this version.` : ''}
            </p>
          </div>
        </section>
        <Card>
          <CardHeader icon={<InfoIcon />} title="How a forecast is made" />
          <ol className="space-y-3.5">
            {STEPS.map((s, i) => (
              <li key={s.title} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/30 text-[12px] font-semibold text-brand-300">
                  {i + 1}
                </span>
                <span>
                  <span className="block text-[14px] font-medium text-white">{s.title}</span>
                  <span className="block text-[13px] text-slate-400">{s.body}</span>
                </span>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
        <Card>
          <CardHeader
            icon={<BarsIcon />}
            title="Model Comparison"
            subtitle="Every candidate on the same unseen matches. Lower is better except accuracy."
          />
          {!match ? (
            <EmptyNote>No match-level backtest stored yet.</EmptyNote>
          ) : (
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[560px] text-[13.5px]">
                <thead>
                  <tr className="border-b border-ink-700 text-left text-[12.5px] text-slate-400">
                    <th className="py-2 font-medium">Model</th>
                    <th className="py-2 text-right font-medium" title="Main metric: penalises confident wrong calls">Log loss</th>
                    <th className="py-2 text-right font-medium">Brier</th>
                    <th className="py-2 text-right font-medium" title="Ranked probability score">RPS</th>
                    <th className="py-2 text-right font-medium">Accuracy</th>
                    <th className="py-2 text-right font-medium" title="Expected calibration error">Calib.</th>
                  </tr>
                </thead>
                <tbody>
                  {MODEL_ORDER.filter((m) => overall[m]).map((m) => {
                    const r = overall[m]
                    const isProd = m === PROD
                    return (
                      <tr key={m} className={`border-b border-ink-700/40 last:border-0 ${isProd ? 'bg-brand-600/10' : ''}`}>
                        <td className="py-2.5 text-white">
                          <span className="flex items-center gap-2">
                            {isProd && <CheckIcon size={15} className="text-brand-300" aria-label="production model" />}
                            {MODEL_LABEL[m] ?? m}
                          </span>
                        </td>
                        <td className="tabular py-2.5 text-right text-slate-200">{r.log_loss.toFixed(4)}</td>
                        <td className="tabular py-2.5 text-right text-slate-200">{r.brier.toFixed(4)}</td>
                        <td className="tabular py-2.5 text-right text-slate-200">{r.rps.toFixed(4)}</td>
                        <td className="tabular py-2.5 text-right text-slate-200">{pct(r.accuracy)}</td>
                        <td className="tabular py-2.5 text-right text-slate-200">{pct(r.ece)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <p className="mt-3 text-[12px] text-slate-500">
                Poisson beat Elo significantly; blending the two did not help on test data, so the simpler model is
                used. Full details: docs/backtest-report.md.
              </p>
            </div>
          )}
        </Card>
        <Card>
          <CardHeader
            icon={<TargetIcon />}
            title="Calibration"
            subtitle="When the model says 40%, it should happen about 40% of the time. Dots near the dashed line = honest probabilities."
          />
          {calibration.length ? <CalibrationChart bins={calibration} /> : <EmptyNote>No calibration data.</EmptyNote>}
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader icon={<TrendIcon />} title="By Competition" subtitle="Log loss of the production model vs league averages (lower is better)." />
          <ul className="space-y-3">
            {(['EPL', 'LA_LIGA', 'BUNDESLIGA', 'SERIE_A', 'UCL'] as CompetitionCode[])
              .filter((c) => byComp[c])
              .map((c) => {
                const m = byComp[c][PROD]
                const b = byComp[c]['base rates']
                const gain = (b - m) / b
                return (
                  <li key={c} className="text-[13.5px]">
                    <div className="mb-1 flex justify-between">
                      <span className="text-white">{COMPETITION_SHORT[c]}</span>
                      <span className="tabular text-slate-300">
                        {m.toFixed(3)} <span className="text-slate-500">vs {b.toFixed(3)}</span>
                        <span className="ml-2 text-good">−{pct(gain)}</span>
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
                      <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(1, gain / 0.15) * 100}%` }} />
                    </div>
                  </li>
                )
              })}
          </ul>
        </Card>
        <Card>
          <CardHeader
            icon={<BarsIcon />}
            title="Season Forecasts, Tested"
            subtitle={`Forecasts made at four points of ${(season?.test_window as { season?: string })?.season ?? 'a past season'}, scored against how it ended.`}
          />
          {!seasonRow ? (
            <EmptyNote>No season-level backtest stored yet.</EmptyNote>
          ) : (
            <div className="grid grid-cols-2 gap-2.5">
              {[
                { k: 'champion_brier', l: 'Title (Brier)' },
                { k: 'champions_league_brier', l: 'Top four / UCL places (Brier)' },
                { k: 'relegation_brier', l: 'Relegation (Brier)' },
                { k: 'position_rps', l: 'Final position (RPS)' },
              ].map((x) => (
                <div key={x.k} className="rounded-xl border border-ink-700 bg-ink-800/50 px-3 py-3">
                  <p className="tabular text-[20px] font-semibold text-white">{seasonRow[x.k]?.toFixed(3) ?? '–'}</p>
                  <p className="text-[12px] text-slate-400">{x.l}</p>
                </div>
              ))}
              <p className="col-span-2 text-[12px] text-slate-500">
                Lower is better; 0 would be perfect foresight. Strength uncertainty {sd} chosen on 2024/25.
              </p>
            </div>
          )}
        </Card>
      </div>

      {versions.data && versions.data.length > 0 && (
        <Card>
          <CardHeader title="Model Versions" subtitle="Every version that has produced forecasts." />
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[520px] text-[13.5px]">
              <thead>
                <tr className="border-b border-ink-700 text-left text-[12.5px] text-slate-400">
                  <th className="py-2 font-medium">Version</th>
                  <th className="py-2 text-right font-medium">Runs</th>
                  <th className="py-2 text-right font-medium">Published</th>
                  <th className="py-2 text-right font-medium">Last run</th>
                </tr>
              </thead>
              <tbody>
                {versions.data.map((v) => (
                  <tr key={v.model_version} className="border-b border-ink-700/40 last:border-0">
                    <td className="py-2 text-white">
                      v{v.model_version}
                      {v.is_current && (
                        <span className="ml-2 rounded-full bg-brand-600/30 px-2 py-0.5 text-[11px] text-brand-300">current</span>
                      )}
                    </td>
                    <td className="tabular py-2 text-right text-slate-300">{v.runs}</td>
                    <td className="tabular py-2 text-right text-slate-300">{v.published_runs}</td>
                    <td className="py-2 text-right text-slate-400">{fmtDate(v.last_run_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <Disclaimer />
    </div>
  )
}
