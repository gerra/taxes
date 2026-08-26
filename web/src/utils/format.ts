export function gbp(value: string | number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (Number.isNaN(n)) return '—'
  return n.toLocaleString('en-GB', {
    style: 'currency',
    currency: 'GBP',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function num(value: string | number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (Number.isNaN(n)) return '—'
  // Trim trailing zeros for quantities like "50.000000"
  const fixed = n.toFixed(decimals)
  return parseFloat(fixed).toLocaleString('en-GB', { maximumFractionDigits: decimals })
}

export function pct(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''))
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Last tax year that has fully elapsed (tax year Y = 6 Apr Y to 5 Apr Y+1)
export function lastElapsedTaxYear(today = new Date()): number {
  const year = today.getFullYear()
  const pastApril5 = today.getMonth() > 3 || (today.getMonth() === 3 && today.getDate() >= 6)
  return pastApril5 ? year - 1 : year - 2
}
