import { useEffect, useState } from 'react'

export interface Loadable<T> {
  data: T | undefined
  error: Error | undefined
  loading: boolean
}

/** Run an async loader whenever `deps` change; ignores results from stale calls. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ data: undefined, error: undefined, loading: true })
  useEffect(() => {
    let alive = true
    setState((s) => ({ data: s.data, error: undefined, loading: true }))
    load().then(
      (data) => alive && setState({ data, error: undefined, loading: false }),
      (error: Error) => alive && setState({ data: undefined, error, loading: false }),
    )
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}
