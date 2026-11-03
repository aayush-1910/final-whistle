/**
 * Backend API client. All requests go to the FastAPI backend via the Vite
 * proxy (/api → localhost:8000). Never call football data providers from
 * the browser — keys stay on the backend.
 */

export interface HealthResponse {
  status: string
  service: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch('/api/v1/health', { signal })
  if (!res.ok) throw new Error(`Health check failed: HTTP ${res.status}`)
  return (await res.json()) as HealthResponse
}
