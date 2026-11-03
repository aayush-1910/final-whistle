import { useState, type ReactNode } from 'react'
import { MenuIcon } from './components/icons'
import { SearchBox } from './components/SearchBox'
import { Sidebar } from './components/Sidebar'
import { useRoute } from './hooks/useRoute'
import { CompetitionsPage } from './pages/Competitions'
import { DataCentrePage } from './pages/DataCentre'
import { MatchPredictorPage } from './pages/MatchPredictor'
import { ModelIntelligencePage } from './pages/ModelIntelligence'
import { OverviewPage } from './pages/Overview'
import { TeamExplorerPage } from './pages/TeamExplorer'
import { UclSimulatorPage } from './pages/UclSimulator'

const PAGES: Record<string, { title: string; subtitle: string; render: (args: string[]) => ReactNode }> = {
  '': {
    title: 'Overview',
    subtitle: 'Live forecasts, title probabilities and key insights across five major competitions.',
    render: () => <OverviewPage />,
  },
  competitions: {
    title: 'Competitions',
    subtitle: 'Full season forecasts: every club, every finishing position, every zone.',
    render: ([code]) => <CompetitionsPage code={code} />,
  },
  'match-predictor': {
    title: 'Match Predictor',
    subtitle: 'Win, draw and loss probabilities, expected goals and likely scorelines.',
    render: ([id]) => <MatchPredictorPage fixtureId={id ? Number(id) : undefined} />,
  },
  ucl: {
    title: 'UCL Simulator',
    subtitle: 'The Champions League simulated to the final, round by round.',
    render: () => <UclSimulatorPage />,
  },
  teams: {
    title: 'Team Explorer',
    subtitle: 'Every club’s outlook, form and how its forecast has moved this season.',
    render: ([id]) => <TeamExplorerPage teamId={id ? Number(id) : undefined} />,
  },
  model: {
    title: 'Model Intelligence',
    subtitle: 'How the model works and how well it has predicted matches it had never seen.',
    render: () => <ModelIntelligencePage />,
  },
  data: {
    title: 'Data Centre',
    subtitle: 'Where the numbers come from, how fresh they are and every import run.',
    render: () => <DataCentrePage />,
  },
}

export default function App() {
  const [page = '', ...args] = useRoute()
  const [menuOpen, setMenuOpen] = useState(false)
  const current = PAGES[page] ?? PAGES['']
  const activeKey = PAGES[page] ? page : ''

  return (
    <div className="min-h-screen">
      <Sidebar active={activeKey} open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="min-w-0 lg:pl-[260px]">
        <header className="flex flex-wrap items-center gap-4 px-5 pt-5 pb-2 sm:px-7">
          <button
            className="rounded-lg border border-ink-700 p-2 text-slate-300 lg:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
          >
            <MenuIcon />
          </button>
          <div className="min-w-0 flex-1 basis-[220px]">
            <h1 className="text-[28px] leading-tight font-semibold tracking-tight text-white">{current.title}</h1>
            <p className="mt-0.5 text-[15px] text-slate-300">{current.subtitle}</p>
          </div>
          <div className="w-full md:w-auto">
            <SearchBox />
          </div>
        </header>
        <main className="px-5 pt-4 pb-10 sm:px-7">{current.render(args)}</main>
      </div>
    </div>
  )
}
