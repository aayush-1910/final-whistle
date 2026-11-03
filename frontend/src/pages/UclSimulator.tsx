import { BallIcon, InfoIcon, TrendIcon, TrophyIcon } from '../components/icons'
import { TimelineChart } from '../components/TimelineChart'
import { Card, CardHeader, Crest, Disclaimer, Emblem, ErrorNote, LoadingRows, Meter, RunMeta } from '../components/ui'
import { useCompetition } from '../hooks/useSeasonData'
import { pct, ROUND_LABEL, ROUND_SHORT, teamName } from '../lib/format'

/** Cell shaded by probability (single-hue sequential); the number is always printed. */
function HeatCell({ p }: { p: number | undefined }) {
  const v = p ?? 0
  return (
    <td className="px-0.5 py-1">
      <span
        className="tabular block rounded-md px-1.5 py-1 text-center text-[12.5px] text-white"
        style={{ background: v < 0.0005 ? 'transparent' : `rgba(139, 92, 246, ${0.1 + Math.min(1, v) * 0.75})` }}
      >
        {v < 0.0005 ? <span className="text-slate-600">–</span> : pct(v)}
      </span>
    </td>
  )
}

export function UclSimulatorPage() {
  const { data, error } = useCompetition('UCL')
  if (error) return <ErrorNote error={error} />
  if (!data) return <LoadingRows rows={12} />
  const f = data.forecast
  const rounds = f.rounds ?? ['round_of_16', 'quarter_finals', 'semi_finals', 'final', 'winner']
  const teams = f.teams // API: sorted by P(win)
  const fav = teams[0]
  const played = Math.max(...teams.map((t) => t.played))
  const matchdays = 8
  const top8 = (t: (typeof teams)[number]) => t.zone_probs.round_of_16 ?? 0
  const playoff = (t: (typeof teams)[number]) => t.zone_probs.knockout_playoffs ?? 0
  const out = (t: (typeof teams)[number]) => t.zone_probs.eliminated ?? 0

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        <section className="card relative overflow-hidden p-6">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_85%_10%,rgba(139,92,246,0.45),transparent_55%)]" />
          <div className="relative">
            <div className="flex items-center gap-3">
              <Emblem url={data.summary.emblem_url} code="UCL" size={34} />
              <span className="text-[15px] font-semibold text-white">UEFA Champions League {f.season_label}</span>
            </div>
            <h2 className="mt-4 text-[28px] font-bold text-white">Who lifts the trophy?</h2>
            <p className="mt-1 text-[14px] text-slate-300">
              {f.run.simulation_count.toLocaleString()} simulations of every remaining match, the knockout draw
              and the final.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-6">
              <a href={`#/teams/${fav.team.id}`} className="flex items-center gap-4">
                <Crest team={fav.team} size={60} />
                <span>
                  <span className="block text-[21px] font-semibold text-white">{teamName(fav.team)}</span>
                  <span className="block text-[13px] text-slate-400">Current favourite</span>
                </span>
              </a>
              <span>
                <span className="tabular block bg-gradient-to-r from-brand-400 to-brand-300 bg-clip-text text-[40px] leading-none font-bold text-transparent">
                  {pct(fav.round_probs?.winner)}
                </span>
                <span className="mt-1 block text-[13px] text-slate-300">Win probability</span>
              </span>
            </div>
            <RunMeta run={f.run} className="mt-6 border-t border-ink-700/70 pt-4" />
          </div>
        </section>
        <Card>
          <CardHeader icon={<InfoIcon />} title="Where the competition stands" />
          <div className="space-y-4 text-[13.5px]">
            <div>
              <div className="mb-1.5 flex justify-between text-slate-300">
                <span>League phase</span>
                <span className="tabular text-white">
                  Matchday {played} of {matchdays}
                </span>
              </div>
              <Meter value={played / matchdays} />
            </div>
            <ul className="space-y-2.5 text-slate-300">
              <li>
                <b className="text-white">1st–8th</b> go straight to the round of 16.
              </li>
              <li>
                <b className="text-white">9th–24th</b> play a two-legged knockout play-off for the other eight places.
              </li>
              <li>
                <b className="text-white">25th–36th</b> are eliminated.
              </li>
              <li>
                Then: round of 16, quarter-finals, semi-finals (two legs each) and a one-off final. The bracket
                follows the league-phase ranking.
              </li>
            </ul>
          </div>
        </Card>
      </div>

      <div className="grid gap-5 2xl:grid-cols-[1.55fr_1fr]">
        <Card>
          <CardHeader
            icon={<TrophyIcon />}
            title="Round by Round"
            subtitle="Chance of finishing in each league-phase zone and of reaching each knockout round."
          />
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[820px] text-[13px]">
              <thead>
                <tr className="border-b border-ink-700 text-[12px] text-slate-400">
                  <th className="py-2 text-left font-medium">#</th>
                  <th className="py-2 text-left font-medium">Team</th>
                  <th className="py-2 text-right font-medium">Pts</th>
                  <th className="px-1 py-2 text-center font-medium" title="Finish 1st–8th">Top 8</th>
                  <th className="px-1 py-2 text-center font-medium" title="Finish 9th–24th">Play-off</th>
                  <th className="px-1 py-2 text-center font-medium" title="Finish 25th–36th">Out</th>
                  {rounds.map((r) => (
                    <th key={r} className="px-1 py-2 text-center font-medium" title={ROUND_LABEL[r]}>
                      {ROUND_SHORT[r]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {teams.map((t, i) => (
                  <tr key={t.team.id} className="border-b border-ink-700/40 last:border-0 hover:bg-ink-800/40">
                    <td className="py-1 pr-2 text-slate-400">{i + 1}</td>
                    <td className="py-1">
                      <a href={`#/teams/${t.team.id}`} className="flex items-center gap-2.5 text-white hover:text-brand-300">
                        <Crest team={t.team} size={20} />
                        <span className="truncate">{teamName(t.team)}</span>
                      </a>
                    </td>
                    <td className="tabular py-1 text-right text-slate-200">{t.current_points}</td>
                    <HeatCell p={top8(t)} />
                    <HeatCell p={playoff(t)} />
                    <HeatCell p={out(t)} />
                    {rounds.map((r) => (
                      <HeatCell key={r} p={t.round_probs?.[r]} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="space-y-5">
          <Card>
            <CardHeader icon={<TrendIcon />} title="Win Probability Timeline" subtitle="After each league-phase matchday." />
            {data.timeline ? <TimelineChart timeline={data.timeline} height={240} /> : <LoadingRows rows={5} />}
          </Card>
          <Card>
            <CardHeader icon={<BallIcon />} title="Road to the Final" subtitle="The five favourites, round by round." />
            <ul className="space-y-4">
              {teams.slice(0, 5).map((t) => (
                <li key={t.team.id}>
                  <p className="mb-1.5 flex items-center gap-2 text-[13.5px] text-white">
                    <Crest team={t.team} size={20} /> {teamName(t.team)}
                  </p>
                  <div className="grid grid-cols-5 gap-1.5">
                    {rounds.map((r) => (
                      <div key={r} title={`${ROUND_LABEL[r]}: ${pct(t.round_probs?.[r])}`}>
                        <Meter value={t.round_probs?.[r] ?? 0} />
                        <p className="mt-1 flex justify-between text-[10.5px] text-slate-500">
                          <span>{ROUND_SHORT[r]}</span>
                          <span className="tabular text-slate-300">{pct(t.round_probs?.[r], 0)}</span>
                        </p>
                      </div>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
      <Disclaimer />
    </div>
  )
}
