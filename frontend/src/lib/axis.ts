/** A 0..max probability axis with round ticks (5/10/20/25% steps). */
export function percentAxis(maxValue: number): { domain: [number, number]; ticks: number[] } {
  const steps = [0.05, 0.1, 0.2, 0.25]
  const target = Math.min(1, maxValue * 1.08 + 0.005)
  const step = steps.find((s) => target / s <= 5) ?? 0.25
  const top = Math.min(1, Math.ceil(target / step) * step)
  const ticks: number[] = []
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Math.round(v * 1000) / 1000)
  return { domain: [0, top], ticks }
}
