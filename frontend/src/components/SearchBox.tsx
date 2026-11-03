import { useEffect, useMemo, useRef, useState } from 'react'
import { navigate } from '../hooks/useRoute'
import { COMPETITION_LABEL, COMPETITION_SHORT, teamName } from '../lib/format'
import { api, COMPETITION_CODES, type CompetitionCode, type TeamRef } from '../services/api'
import { Crest, Emblem } from './ui'
import { SearchIcon } from './icons'

interface Item {
  key: string
  label: string
  detail: string
  href: string
  team?: TeamRef
  code?: CompetitionCode
  emblem?: string | null
}

/** Teams and competitions, built from the published forecasts (the clubs in play this season). */
async function loadIndex(): Promise<Item[]> {
  const comps = await api.competitions()
  const items: Item[] = comps.map((c) => ({
    key: `c-${c.code}`,
    label: COMPETITION_LABEL[c.code],
    detail: c.country ?? 'Europe',
    href: `/competitions/${c.code}`,
    code: c.code,
    emblem: c.emblem_url,
  }))
  const teams = new Map<number, { team: TeamRef; comps: CompetitionCode[] }>()
  await Promise.all(
    comps
      .filter((c) => c.current_season && c.latest_published_run)
      .map(async (c) => {
        const f = await api.forecast(c.code, c.current_season!)
        for (const t of f.teams) {
          const e = teams.get(t.team.id) ?? { team: t.team, comps: [] }
          e.comps.push(c.code)
          teams.set(t.team.id, e)
        }
      }),
  )
  for (const { team, comps: cs } of teams.values()) {
    items.push({
      key: `t-${team.id}`,
      label: teamName(team),
      detail: cs
        .sort((a, b) => COMPETITION_CODES.indexOf(a) - COMPETITION_CODES.indexOf(b))
        .map((c) => COMPETITION_SHORT[c])
        .join(' · '),
      href: `/teams/${team.id}`,
      team,
    })
  }
  return items
}

const norm = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()

export function SearchBox() {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState<Item[]>([])
  const [cursor, setCursor] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open && index.length === 0) loadIndex().then(setIndex, () => undefined)
  }, [open, index.length])

  const results = useMemo(() => {
    const q = norm(query.trim())
    if (!q) return []
    return index
      .filter((it) => norm(it.label).includes(q) || (it.team && norm(it.team.name).includes(q)))
      .sort((a, b) => Number(!norm(a.label).startsWith(q)) - Number(!norm(b.label).startsWith(q)))
      .slice(0, 8)
  }, [query, index])

  const go = (it: Item) => {
    navigate(it.href)
    setQuery('')
    setOpen(false)
    input.current?.blur()
  }

  return (
    <div className="relative w-full md:w-[380px]">
      <div className="flex items-center gap-2.5 rounded-xl border border-ink-700 bg-ink-850 px-3.5 py-2.5 focus-within:border-brand-500">
        <SearchIcon size={18} className="text-slate-400" />
        <input
          ref={input}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setCursor(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') setCursor((c) => Math.min(c + 1, results.length - 1))
            else if (e.key === 'ArrowUp') setCursor((c) => Math.max(c - 1, 0))
            else if (e.key === 'Enter' && results[cursor]) go(results[cursor])
            else if (e.key === 'Escape') input.current?.blur()
          }}
          placeholder="Search teams, competitions..."
          aria-label="Search teams and competitions"
          className="min-w-0 flex-1 bg-transparent text-[14px] text-slate-100 outline-none placeholder:text-slate-500"
        />
        <span className="hidden items-center gap-1 sm:flex">
          <kbd className="rounded-md border border-ink-600 bg-ink-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            Ctrl
          </kbd>
          <kbd className="rounded-md border border-ink-600 bg-ink-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            K
          </kbd>
        </span>
      </div>
      {open && query.trim() && (
        <ul className="absolute right-0 left-0 z-50 mt-2 overflow-hidden rounded-xl border border-ink-700 bg-ink-850 py-1 shadow-2xl shadow-black/60">
          {results.length === 0 && (
            <li className="px-4 py-3 text-[13px] text-slate-400">
              {index.length ? 'No matches.' : 'Loading…'}
            </li>
          )}
          {results.map((it, i) => (
            <li key={it.key}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => go(it)}
                onMouseEnter={() => setCursor(i)}
                className={`flex w-full items-center gap-3 px-4 py-2.5 text-left ${i === cursor ? 'bg-ink-800' : ''}`}
              >
                {it.team ? <Crest team={it.team} size={24} /> : <Emblem url={it.emblem} code={it.code!} size={24} />}
                <span className="min-w-0">
                  <span className="block truncate text-[14px] text-white">{it.label}</span>
                  <span className="block truncate text-[12px] text-slate-400">{it.detail}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
