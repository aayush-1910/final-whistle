import { BackendStatus } from './components/BackendStatus'

const COMPETITIONS = [
  'Premier League',
  'La Liga',
  'Bundesliga',
  'Serie A',
  'UEFA Champions League',
]

export default function App() {
  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-pitch-800 py-5">
        <h1 className="text-xl font-semibold tracking-tight">
          ⚽ Final Whistle <span className="text-slate-500">· 2026/27</span>
        </h1>
        <BackendStatus />
      </header>

      <main className="flex-1 py-10">
        <section className="rounded-lg border border-pitch-800 bg-pitch-900 p-6">
          <h2 className="text-lg font-medium">Forecasts are not available yet</h2>
          <p className="mt-2 max-w-prose text-slate-400">
            The prediction engine is still being built. Probabilities will appear here once
            they come from real data and a tested model run. Until then, nothing on this
            page is a prediction.
          </p>
        </section>

        <section className="mt-8">
          <h2 className="text-sm font-medium tracking-wide text-slate-500 uppercase">
            Competitions in scope
          </h2>
          <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {COMPETITIONS.map((name) => (
              <li
                key={name}
                className="rounded-lg border border-pitch-800 bg-pitch-900 px-4 py-3 text-slate-300"
              >
                {name}
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="border-t border-pitch-800 py-5 text-xs text-slate-500">
        Independent project. Not affiliated with any league, club, UEFA or data provider.
      </footer>
    </div>
  )
}
