import { useEffect, useState } from 'react'

/** Minimal hash router: "#/teams/57" -> ["teams", "57"]. */
export function useRoute(): string[] {
  const parse = () =>
    window.location.hash
      .replace(/^#\/?/, '')
      .split('/')
      .filter(Boolean)
  const [parts, setParts] = useState(parse)
  useEffect(() => {
    const onChange = () => {
      setParts(parse())
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return parts
}

export function navigate(path: string): void {
  window.location.hash = path.startsWith('/') ? path : `/${path}`
}
