import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { History, HistoryYear } from '../types'
import { gbp, shortDate } from '../utils/format'

/** Estimate against what HMRC actually charged, year by year.
 *
 * A single year's page can only tell you what this tool thinks you owe. Only
 * the comparison tells you whether the return you actually filed agreed — and
 * a gap is worth chasing in either direction: it means either the return went
 * in on different figures, or this tool has something wrong.
 *
 * The "actually paid" figure is typed in here, in the row it explains. It used
 * to be one of twenty boxes on the Planner form — a figure that feeds no
 * calculation, entered months after everything else, three tabs from the only
 * table that shows it. */
export default function HistoryView({ onChange }: { onChange: () => void }) {
  const [data, setData] = useState<History | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api
      .get<History>('/api/history')
      .then(setData)
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(load, [load])

  const saveActual = async (taxYear: number, value: string) => {
    await api.put(`/api/history/${taxYear}/actual`, {
      actual_tax_paid: value === '' ? null : Number(value),
    })
    load()
    onChange()
  }

  if (error) return <p className="error-text">{error}</p>
  if (!data) return <p className="muted">Loading…</p>

  const compared = data.years.filter((y) => y.actual !== null)

  return (
    <div>
      <header className="step-head">
        <div className="page-head">
          <h2>History</h2>
        </div>
        <p className="step-purpose">
          Every year at once: what this tool estimates against what HMRC actually charged. The one
          check that catches a year filed on the wrong figures.
        </p>
      </header>
      <p className="muted small">{data.explain}</p>

      {data.years.length === 0 && (
        <p className="muted">
          Nothing to compare yet — run a calculation or enter your income for a year first.
        </p>
      )}

      {data.years.length > 0 && (
        <table className="sa-table history-table">
          <thead>
            <tr>
              <th>Year</th>
              <th className="num">Estimated bill</th>
              <th className="num">Investment only</th>
              <th className="num">PAYE shortfall</th>
              <th className="num">Actually paid</th>
              <th className="num">Difference</th>
              <th>Due</th>
            </tr>
          </thead>
          <tbody>
            {data.years.map((y) => (
              <HistoryRow key={y.tax_year} year={y} onSave={saveActual} />
            ))}
          </tbody>
        </table>
      )}

      {compared.length === 0 && data.years.length > 0 && (
        <div className="banner info">
          Nothing to compare against yet. Type what HMRC charged into the <b>Actually paid</b>{' '}
          column above — it is the only figure in this app that has to be typed in, because HMRC
          publishes no way to read it and deriving it from this tool&rsquo;s own estimate would make
          the comparison circular. You&rsquo;ll find it on your HMRC statement, under &ldquo;Your
          Self Assessment account&rdquo;.
        </div>
      )}

      {data.mismatched.length > 0 && (
        <div className="banner warn">
          <b>
            {data.mismatched.length} year{data.mismatched.length === 1 ? '' : 's'} disagree with
            what you paid.
          </b>{' '}
          A positive difference means you paid HMRC more than these figures say was due — usually a
          credit you were entitled to and did not claim. A negative one means you paid less: income
          left off the return, or a credit claimed that was not due. Open the year and compare its
          breakdown against the return you filed.
        </div>
      )}

      {data.unreconciled.length > 0 && (
        <div className="banner info">
          No P60 entered for{' '}
          {data.unreconciled
            .map((y) => `${y}/${String((y + 1) % 100).padStart(2, '0')}`)
            .join(', ')}
          , so those estimates cover investment income only and will read low wherever PAYE
          under-collected on salary. Switch the year picker to one of them and fill in the Income
          step to close the gap.
        </div>
      )}
    </div>
  )
}

/** One year, with its "actually paid" cell editable in place.
 *
 * Committed on blur or Enter, so the figure lands next to the difference it
 * moves — the entire point of the row. */
function HistoryRow({
  year,
  onSave,
}: {
  year: HistoryYear
  onSave: (taxYear: number, value: string) => Promise<void>
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const stored = year.actual === null ? '' : String(year.actual)
  const value = draft ?? stored

  const commit = async () => {
    if (draft === null || draft === stored) {
      setDraft(null)
      return
    }
    setBusy(true)
    try {
      await onSave(year.tax_year, draft.trim())
      setDraft(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>{year.label}</td>
      <td className="num">
        <b>{gbp(year.estimate)}</b>
      </td>
      <td className="num muted">{gbp(year.investment_only)}</td>
      <td className="num muted">{year.reconciled ? gbp(year.employment_shortfall) : 'no P60'}</td>
      <td className="num">
        <input
          className="actual-input"
          type="number"
          inputMode="decimal"
          placeholder="—"
          aria-label={`What HMRC actually charged for ${year.label}`}
          title="From your HMRC statement. Feeds nothing but this comparison."
          disabled={busy}
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur()
            if (e.key === 'Escape') setDraft(null)
          }}
        />
      </td>
      <td className={`num ${year.difference !== null && !year.matches ? 'ledger-negative' : ''}`}>
        {year.difference === null ? '—' : gbp(year.difference)}
      </td>
      <td className="muted small">{shortDate(year.due_date)}</td>
    </tr>
  )
}
