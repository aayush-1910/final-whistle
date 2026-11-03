import type { ReactNode } from 'react'
import { useApi } from '../hooks/useApi'
import { timeAgo } from '../lib/format'
import { api } from '../services/api'
import {
  BallIcon,
  BarsIcon,
  CloseIcon,
  DatabaseIcon,
  HomeIcon,
  ShieldIcon,
  TargetIcon,
  TrophyIcon,
} from './icons'

const NAV: { section: string; items: { key: string; label: string; icon: ReactNode }[] }[] = [
  {
    section: 'Workspace',
    items: [
      { key: '', label: 'Overview', icon: <HomeIcon /> },
      { key: 'competitions', label: 'Competitions', icon: <TrophyIcon /> },
      { key: 'match-predictor', label: 'Match Predictor', icon: <TargetIcon /> },
      { key: 'ucl', label: 'UCL Simulator', icon: <BallIcon /> },
      { key: 'teams', label: 'Team Explorer', icon: <ShieldIcon /> },
    ],
  },
  {
    section: 'Intelligence',
    items: [
      { key: 'model', label: 'Model Intelligence', icon: <BarsIcon /> },
      { key: 'data', label: 'Data Centre', icon: <DatabaseIcon /> },
    ],
  },
]

export function Logo() {
  return (
    <a href="#/" className="flex items-center gap-3">
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-[0_0_24px_-4px_var(--color-brand-600)]">
        <BallIcon size={26} strokeWidth={1.6} />
      </span>
      <span className="leading-tight">
        <span className="block text-[19px] font-bold tracking-tight whitespace-nowrap text-white">FINAL WHISTLE</span>
        <span className="block text-[10.5px] font-medium tracking-[0.06em] whitespace-nowrap text-slate-300">
          FOOTBALL INTELLIGENCE
        </span>
      </span>
    </a>
  )
}

function SystemStatus() {
  const health = useApi(() => api.health(), [])
  const comps = useApi(() => api.competitions(), [])
  const online = health.data?.database === 'ok'
  const last = comps.data
    ?.map((c) => c.freshness.last_ingested_at)
    .filter((x): x is string => !!x)
    .sort()
    .pop()
  const stale = comps.data?.some((c) => c.current_season && c.freshness.is_stale)
  const label = health.loading ? 'Checking…' : online ? (stale ? 'Data is stale' : 'System Online') : 'Backend offline'
  const dot = health.loading ? 'bg-slate-500' : online ? (stale ? 'bg-warn' : 'bg-good') : 'bg-bad'
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-850/80 p-3.5" role="status">
      <div className="flex items-center gap-3">
        <span className={`h-3 w-3 shrink-0 rounded-full ${dot} shadow-[0_0_10px] shadow-current`} />
        <div className="min-w-0">
          <p className="text-[14px] font-medium text-white">{label}</p>
          <p className="truncate text-[12px] text-slate-400">
            {last ? `Data synced ${timeAgo(last)}` : online ? 'No data imported yet' : 'Start it with dev.cmd'}
          </p>
        </div>
      </div>
    </div>
  )
}

export function Sidebar({ active, open, onClose }: { active: string; open: boolean; onClose: () => void }) {
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={onClose} aria-hidden />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[260px] flex-col border-r border-ink-700/60 bg-gradient-to-b from-ink-900 via-ink-900 to-[#170f33] px-4 pt-6 pb-5 transition-transform lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-2">
          <Logo />
          <button className="text-slate-400 lg:hidden" onClick={onClose} aria-label="Close menu">
            <CloseIcon />
          </button>
        </div>
        <nav className="mt-9 flex-1 space-y-7 overflow-y-auto scroll-thin">
          {NAV.map((group) => (
            <div key={group.section}>
              <p className="mb-2 px-3 text-[13px] font-medium text-slate-400">{group.section}</p>
              <ul className="space-y-1">
                {group.items.map((it) => {
                  const isActive = it.key === active
                  return (
                    <li key={it.key}>
                      <a
                        href={`#/${it.key}`}
                        onClick={onClose}
                        aria-current={isActive ? 'page' : undefined}
                        className={`flex items-center gap-3.5 rounded-xl px-3.5 py-2.5 text-[15px] transition-colors ${
                          isActive
                            ? 'bg-gradient-to-r from-brand-600 to-brand-500/80 font-medium text-white shadow-[0_0_24px_-8px_var(--color-brand-500)]'
                            : 'text-slate-300 hover:bg-ink-800 hover:text-white'
                        }`}
                      >
                        <span className={isActive ? 'text-white' : 'text-slate-400'}>{it.icon}</span>
                        {it.label}
                      </a>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>
        <SystemStatus />
      </aside>
    </>
  )
}
