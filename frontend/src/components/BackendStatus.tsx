import { useEffect, useState } from 'react'
import { fetchHealth } from '../services/api'

type State = 'checking' | 'online' | 'offline'

const STYLES: Record<State, { dot: string; label: string }> = {
  checking: { dot: 'bg-slate-400', label: 'Checking backend…' },
  online: { dot: 'bg-emerald-400', label: 'Backend online' },
  offline: { dot: 'bg-red-400', label: 'Backend offline' },
}

export function BackendStatus() {
  const [state, setState] = useState<State>('checking')

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then(() => setState('online'))
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          console.error(err)
          setState('offline')
        }
      })
    return () => controller.abort()
  }, [])

  const { dot, label } = STYLES[state]
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-400" role="status">
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      {label}
    </span>
  )
}
