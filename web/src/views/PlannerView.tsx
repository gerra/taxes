import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { PlannerData, Tip } from '../types'
import { gbp, pct, shortDate } from '../utils/format'

const FIELDS: { key: string; label: string; hint?: string }[] = [
  { key: 'employment_income', label: 'Employment income (P60 “pay”)' },
  { key: 'other_income', label: 'Other taxable income' },
  { key: 'other_interest', label: 'Interest not in the report (other banks)' },
  { key: 'pension_employee', label: 'Pension via payroll — your contributions' },
  { key: 'pension_employer', label: 'Pension via payroll — employer contributions' },
  { key: 'sipp_paid', label: 'SIPP paid personally (net)', hint: 'HMRC adds 25% on top' },
  { key: 'gift_aid_paid', label: 'Gift Aid donations (net)' },
  { key: 'isa_used', label: 'ISA allowance already used this year' },
  { key: 'pension_prior_1', label: 'Pension total, last year', hint: 'for carry-forward' },
  { key: 'pension_prior_2', label: 'Pension total, 2 years ago' },
  { key: 'pension_prior_3', label: 'Pension total, 3 years ago' },
]

export default function PlannerView({ year }: { year: number }) {
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [data, setData] = useState<PlannerData | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const loadPlanner = useCallback(() => {
    api
      .get<PlannerData>(`/api/planner/${year}`)
      .then(setData)
      .catch((e) => setError(String(e)))
  }, [year])

  useEffect(() => {
    setData(null)
    api.get<Record<string, number> | null>(`/api/planner/${year}/inputs`).then((saved) => {
      const asStrings: Record<string, string> = {}
      for (const [k, v] of Object.entries(saved ?? {})) asStrings[k] = String(v)
      setInputs(asStrings)
      loadPlanner()
    })
  }, [year, loadPlanner])

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const body: Record<string, number> = {}
      for (const [k, v] of Object.entries(inputs)) {
        if (v !== '') body[k] = parseFloat(v)
      }
      await api.put(`/api/planner/${year}/inputs`, body)
      loadPlanner()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <h2>
          Planner {year}/{String((year + 1) % 100).padStart(2, '0')}
        </h2>
      </div>

      <section className="card">
        <h3>Your income & contributions</h3>
        <div className="planner-grid">
          {FIELDS.map((f) => (
            <label key={f.key}>
              {f.label}
              <input
                type="number"
                inputMode="decimal"
                placeholder="0"
                value={inputs[f.key] ?? ''}
                onChange={(e) => setInputs({ ...inputs, [f.key]: e.target.value })}
                title={f.hint}
              />
            </label>
          ))}
        </div>
        <div className="card-actions">
          <button className="btn primary" disabled={saving} onClick={save}>
            {saving ? 'Saving…' : 'Save & recompute'}
          </button>
          {error && <span className="error-text">{error}</span>}
        </div>
      </section>

      {data && (
        <>
          {!data.has_report && (
            <div className="banner info">
              No calculation for this year yet — investment figures are treated as zero. Run the
              Report tab first for accurate tips.
            </div>
          )}
          <ProfileSummary data={data} />
          <h3>Tips</h3>
          {data.tips.length === 0 && (
            <p className="muted">Nothing actionable found — add your income figures above.</p>
          )}
          {data.tips.map((t) => (
            <TipCard key={t.id} tip={t} />
          ))}
        </>
      )}
    </div>
  )
}

function ProfileSummary({ data }: { data: PlannerData }) {
  const p = data.profile
  return (
    <div className="cards-row">
      <div className="stat-card">
        <div className="stat-title">Adjusted net income</div>
        <div className="stat-value">{gbp(p.income.adjusted_net_income, 0)}</div>
        <div className="muted small">
          marginal band: {p.bands.marginal_band}
          {p.bands.in_pa_taper && ' · in the 60% zone'}
        </div>
      </div>
      <div className="stat-card">
        <div className="stat-title">Personal allowance</div>
        <div className="stat-value">{gbp(p.allowances.personal_allowance, 0)}</div>
      </div>
      <div className="stat-card">
        <div className="stat-title">Est. tax on investments</div>
        <div className="stat-value">
          {gbp(p.tax.dividend_tax + p.tax.savings_tax + p.tax.cgt_estimate)}
        </div>
        <div className="muted small">
          dividends {gbp(p.tax.dividend_tax, 0)} · interest {gbp(p.tax.savings_tax, 0)} · CGT{' '}
          {gbp(p.tax.cgt_estimate, 0)}
        </div>
      </div>
      <div className="stat-card">
        <div className="stat-title">Marginal relief rate</div>
        <div className="stat-value">{pct(p.marginal.effective_rate)}</div>
        <div className="muted small">what £1 of pension contribution saves</div>
      </div>
    </div>
  )
}

function TipCard({ tip }: { tip: Tip }) {
  const [open, setOpen] = useState(false)
  return (
    <section className={`card tip-card ${open ? 'open' : ''}`} onClick={() => setOpen(!open)}>
      <div className="card-head">
        <b>{tip.title}</b>
        {tip.estimated_win_gbp != null && (
          <span className="badge ok">save ~{gbp(tip.estimated_win_gbp, 0)}</span>
        )}
      </div>
      <p>{tip.what_to_do}</p>
      {open && (
        <>
          <p className="muted">{tip.why}</p>
          {tip.deadline && <p className="muted small">Deadline: {shortDate(tip.deadline)}</p>}
        </>
      )}
    </section>
  )
}
