import { useEffect, useState } from 'react'
import { api } from '../api'
import type { History } from '../types'
import { gbp, shortDate } from '../utils/format'

/** Estimate against what HMRC actually charged, year by year.
 *
 * A single year's page can only tell you what this tool thinks you owe. Only
 * the comparison tells you whether the return you actually filed agreed — and
 * a gap is worth chasing in either direction: it means either the return went
 * in on different figures, or this tool has something wrong. */
export default function HistoryView() {
  const [data, setData] = useState<History | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get<History>('/api/history')
      .then(setData)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <p className="error-text">{error}</p>
  if (!data) return <p className="muted">Loading…</p>

  const compared = data.years.filter((y) => y.actual !== null)

  return (
    <div>
      <div className="page-head">
        <h2>History</h2>
      </div>
      <p className="muted small">{data.explain}</p>

      {data.years.length === 0 && (
        <p className="muted">
          Nothing to compare yet — run a calculation or fill in the Planner for a year first.
        </p>
      )}

      {data.years.length > 0 && (
        <table className="sa-table">
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
              <tr key={y.tax_year}>
                <td>{y.label}</td>
                <td className="num">
                  <b>{gbp(y.estimate)}</b>
                </td>
                <td className="num muted">{gbp(y.investment_only)}</td>
                <td className="num muted">
                  {y.reconciled ? gbp(y.employment_shortfall) : 'no P60'}
                </td>
                <td className="num">{y.actual === null ? '—' : gbp(y.actual)}</td>
                <td
                  className={`num ${y.difference !== null && !y.matches ? 'ledger-negative' : ''}`}
                >
                  {y.difference === null ? '—' : gbp(y.difference)}
                </td>
                <td className="muted small">{shortDate(y.due_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {compared.length === 0 && data.years.length > 0 && (
        <div className="banner info">
          No years have a &ldquo;what HMRC actually charged&rdquo; figure yet. Add one per year in
          the Planner tab — it is the only figure here that has to be typed in, because HMRC
          publishes no way to read it and deriving it from this tool&rsquo;s own estimate would make
          the comparison circular.
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
          under-collected on salary.
        </div>
      )}
    </div>
  )
}
