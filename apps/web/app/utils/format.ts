export function formatConfidence(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value) || !Number.isFinite(value)) {
    return '\u2014'
  }
  return `${(value * 100).toFixed(1)}%`
}
