import { useState, type ReactNode } from 'react'
import type { CompetitionCode, RunInfo, TeamRef } from '../services/api'
import { COMPETITION_CODES } from '../services/api'
import { COMPETITION_SHORT, fmtDateTime, teamName } from '../lib/format'
import { AlertIcon, ArrowRightIcon, ChevronDownIcon, InfoIcon } from './icons'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card p-5 ${className}`}>{children}</section>
}

export function CardHeader({
  icon,
  title,
  subtitle,
  action,
}: {
  icon?: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        {icon && <span className="mt-0.5 shrink-0 text-brand-400">{icon}</span>}
        <div className="min-w-0">
          <h2 className="text-[17px] font-semibold tracking-tight text-white">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[13px] text-slate-400">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function ViewAll({ href, label = 'View All' }: { href: string; label?: string }) {
  return (
    <a
      href={href}
      className="inline-flex items-center gap-1 text-[13px] font-medium text-brand-400 hover:text-brand-300"
    >
      {label} <ArrowRightIcon size={14} />
    </a>
  )
}

/** Club crest from the data provider, with a monogram fallback. */
export function Crest({ team, size = 28 }: { team: TeamRef; size?: number }) {
  const [broken, setBroken] = useState(false)
  if (!team.crest_url || broken) {
    return (
      <span
        className="inline-flex shrink-0 items-center justify-center rounded-full bg-ink-700 text-[10px] font-semibold text-slate-300"
        style={{ width: size, height: size }}
        aria-hidden
      >
        {(team.tla || teamName(team)).slice(0, 3)}
      </span>
    )
  }
  return (
    <img
      src={team.crest_url}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => setBroken(true)}
      className="shrink-0 object-contain"
      style={{ width: size, height: size }}
    />
  )
}

/** Competition emblem. Provider emblems are dark-on-transparent, so they sit on a light chip. */
export function Emblem({
  url,
  code,
  size = 28,
}: {
  url: string | null | undefined
  code: CompetitionCode
  size?: number
}) {
  const [broken, setBroken] = useState(false)
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-lg bg-white/95 p-1"
      style={{ width: size, height: size }}
      title={COMPETITION_SHORT[code]}
    >
      {url && !broken ? (
        <img src={url} alt="" className="h-full w-full object-contain" onError={() => setBroken(true)} />
      ) : (
        <span className="text-[9px] font-bold text-ink-900">{code.slice(0, 3)}</span>
      )}
    </span>
  )
}

export function ProbPill({ p, children }: { p: number; children: ReactNode }) {
  // Opacity encodes magnitude; the number carries the value (never colour alone).
  const alpha = 0.18 + Math.min(1, p / 0.5) * 0.5
  return (
    <span
      className="tabular inline-block min-w-[60px] rounded-md px-2 py-0.5 text-center text-[13px] font-semibold text-white"
      style={{ backgroundColor: `rgba(124, 58, 237, ${alpha})` }}
    >
      {children}
    </span>
  )
}

export function Meter({ value, className = '' }: { value: number; className?: string }) {
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-ink-700 ${className}`}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-400"
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
    </div>
  )
}

export function CompetitionSelect({
  value,
  onChange,
  codes = COMPETITION_CODES,
}: {
  value: CompetitionCode
  onChange: (c: CompetitionCode) => void
  codes?: CompetitionCode[]
}) {
  return (
    <label className="relative inline-flex items-center">
      <span className="sr-only">Competition</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as CompetitionCode)}
        className="appearance-none rounded-lg border border-ink-700 bg-ink-800 py-1.5 pr-8 pl-3 text-[13px] text-slate-100 outline-none hover:border-ink-600 focus:border-brand-500"
      >
        {codes.map((c) => (
          <option key={c} value={c}>
            {COMPETITION_SHORT[c]}
          </option>
        ))}
      </select>
      <ChevronDownIcon size={14} className="pointer-events-none absolute right-2.5 text-slate-400" />
    </label>
  )
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T
  onChange: (v: T) => void
  items: { value: T; label: ReactNode }[]
}) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-xl border border-ink-700 bg-ink-900 p-1">
      {items.map((it) => (
        <button
          key={it.value}
          type="button"
          onClick={() => onChange(it.value)}
          className={`rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors ${
            it.value === value
              ? 'bg-brand-600 text-white shadow-[0_0_20px_-6px_var(--color-brand-500)]'
              : 'text-slate-400 hover:bg-ink-800 hover:text-slate-200'
          }`}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-ink-800 ${className}`} />
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2.5" aria-busy>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-8" />
      ))}
    </div>
  )
}

export function ErrorNote({ error }: { error: Error }) {
  const offline = /fetch|network|HTTP 50/i.test(error.message)
  return (
    <div className="flex items-start gap-2 rounded-xl border border-bad/30 bg-bad/10 p-3 text-[13px] text-rose-200">
      <AlertIcon size={16} className="mt-0.5 shrink-0" />
      <span>
        {offline
          ? 'Could not reach the Final Whistle backend. Is it running? (double-click dev.cmd)'
          : error.message}
      </span>
    </div>
  )
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-ink-700 bg-ink-800/60 p-3 text-[13px] text-slate-400">
      <InfoIcon size={16} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  )
}

/** Provenance footer: shown next to every probability (README §1). */
export function RunMeta({ run, className = '' }: { run: RunInfo; className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-slate-400 ${className}`}>
      <InfoIcon size={14} className="text-slate-500" />
      <span>Model v{run.model_version}</span>
      <span className="text-ink-600">|</span>
      <span>Forecast: {fmtDateTime(run.run_at)}</span>
      <span className="text-ink-600">|</span>
      <span>Data cutoff: {fmtDateTime(run.data_cutoff)}</span>
      {run.rules_source_quality === 'secondary' && (
        <>
          <span className="text-ink-600">|</span>
          <span title="Tiebreak rules verified from secondary sources">Rules: secondary source</span>
        </>
      )}
    </div>
  )
}

export const Disclaimer = () => (
  <p className="mt-8 text-center text-[12px] text-slate-500">
    Probabilities from a statistical model, not certainties. Final Whistle is an independent project, not
    a betting product, and not affiliated with any league, club, UEFA or data provider.
  </p>
)
