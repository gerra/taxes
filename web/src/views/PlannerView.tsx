import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { PlannerData, Tip } from '../types'
import { gbp, pct, shortDate, taxYearLabel } from '../utils/format'

// Input fields for the planner; prior-year pension rows are named after the
// actual tax years so they match a provider's statement.
const fields = (year: number): { key: string; label: string; where: string }[] => [
  {
    key: 'employment_income',
    label: 'Employment income',
    where:
      'P60 (your employer issues it by 31 May) → “Pay” in the “Pay and Income Tax details” box. Or the final March payslip → “Taxable pay YTD”. This is already net of net-pay pension contributions.',
  },
  {
    key: 'other_income',
    label: 'Other taxable income',
    where:
      'Self-employment profit, rental income, taxable benefits — anything else HMRC taxes as income. Leave 0 if none.',
  },
  {
    key: 'other_interest',
    label: 'Interest not in the report',
    where:
      'Interest from banks you haven’t uploaded statements for. Each bank shows an annual interest summary: HSBC app → account → Statements → “Interest” / annual tax summary; Revolut app → Statements → “Interest paid”.',
  },
  {
    key: 'pension_employee',
    label: 'Pension via payroll — yours',
    where:
      'Your own contributions deducted through salary this tax year: final March payslip → “Pension YTD” (often labelled “EEs Pension” or “AE Pension EE”), or your workplace pension’s annual statement. Payslips show it as a negative deduction — enter it as a positive number, without the “-”.',
  },
  {
    key: 'pension_employer',
    label: 'Pension via payroll — employer',
    where:
      'Employer contributions this tax year: final March payslip → “Employer pension YTD” (often labelled “ERs Pension” or “AE Pension ER”), or the workplace pension’s annual statement. Enter as a positive number. Counts towards the £60,000 annual allowance.',
  },
  {
    key: 'sipp_paid',
    label: 'SIPP paid personally (net)',
    where:
      'What you actually transferred into a personal pension/SIPP this tax year — the provider’s contribution history. Enter the net amount; HMRC adds 25% on top automatically.',
  },
  {
    key: 'gift_aid_paid',
    label: 'Gift Aid donations (net)',
    where:
      'Donations where you ticked Gift Aid — charity receipts, JustGiving/GoFundMe history, payroll-giving excluded.',
  },
  {
    key: 'isa_used',
    label: 'ISA allowance used this year',
    where:
      'Total paid into ISAs (cash + stocks & shares) since 6 April: ISA provider app → “Subscriptions this tax year” / allowance remaining.',
  },
  {
    key: 'pension_prior_1',
    label: `Pension total, ${taxYearLabel(year - 1)}`,
    where: `ALL contributions (yours + employer + SIPP gross) in the ${taxYearLabel(year - 1)} tax year (6 Apr ${year - 1} – 5 Apr ${year}). Sum the contribution rows between those dates in your pension provider's transaction history — transfers in don't count. Needed for carry-forward.`,
  },
  {
    key: 'pension_prior_2',
    label: `Pension total, ${taxYearLabel(year - 2)}`,
    where: `Same for 6 Apr ${year - 2} – 5 Apr ${year - 1}. Unused allowance from this year can be carried forward.`,
  },
  {
    key: 'pension_prior_3',
    label: `Pension total, ${taxYearLabel(year - 3)}`,
    where: `Same for 6 Apr ${year - 3} – 5 Apr ${year - 2} — the oldest year carry-forward can reach.`,
  },
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
        <p className="muted small">
          All figures for the selected tax year (6 Apr – 5 Apr). Hover the{' '}
          <i className="info-icon">i</i> next to each field to see which document it comes from.
        </p>
        <div className="planner-grid">
          {fields(year).map((f) => (
            <label key={f.key}>
              <span className="label-text">
                {f.label}
                <i
                  className="info-icon tip-wrap"
                  data-tip={f.where}
                  aria-label="Where to find this"
                >
                  i
                </i>
              </span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                placeholder="0"
                value={inputs[f.key] ?? ''}
                onChange={(e) => setInputs({ ...inputs, [f.key]: e.target.value })}
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
  const y = data.year
  const reliefs = p.income.total - p.income.adjusted_net_income
  const aniTip =
    `Non-savings income (employment + other) ${gbp(p.income.non_savings, 0)}\n` +
    `+ interest ${gbp(p.income.savings, 0)}\n` +
    `+ dividends ${gbp(p.income.dividends, 0)}\n` +
    `= total income ${gbp(p.income.total, 0)}\n` +
    `− gross pension (SIPP) & Gift Aid relief ${gbp(reliefs, 0)}\n` +
    `= adjusted net income ${gbp(p.income.adjusted_net_income, 0)}\n\n` +
    `Investment figures come from this year's report; enter your P60 pay above to complete the picture.`
  const paTip =
    `Standard allowance ${gbp(y.personal_allowance, 0)}, reduced by £1 for every £2 of adjusted net income above ${gbp(y.pa_taper_start, 0)}.\n` +
    (p.bands.in_pa_taper
      ? `Yours is tapered: ${gbp(p.income.adjusted_net_income, 0)} is ${gbp(p.income.adjusted_net_income - y.pa_taper_start, 0)} over the threshold.`
      : `Yours (${gbp(p.income.adjusted_net_income, 0)}) is below the threshold, so you keep the full allowance.`)
  const taxTip =
    `Income is stacked in HMRC order — non-savings, then interest, then dividends, then gains — and each slice taxed at the band it lands in.\n\n` +
    `Dividends: ${gbp(p.tax.dividend_tax)} after the ${gbp(y.dividend_allowance, 0)} dividend allowance (rates ${pct(y.dividend_rates.basic)} / ${pct(y.dividend_rates.higher)} / ${pct(y.dividend_rates.additional)}).\n` +
    `Interest: ${gbp(p.tax.savings_tax)} after your ${gbp(p.allowances.psa, 0)} personal savings allowance${p.allowances.starting_rate_used > 0 ? ` and ${gbp(p.allowances.starting_rate_used, 0)} starting-rate band` : ''}.\n` +
    `CGT: ${gbp(p.tax.cgt_estimate)} after the ${gbp(y.cgt_allowance, 0)} annual exempt amount — ${pct(y.cgt_rates_shares.basic)} within the basic band, ${pct(y.cgt_rates_shares.higher)} above.\n\n` +
    `Employment tax is already paid via PAYE and isn't included.`
  const marginalTip =
    `Your taxable income (${gbp(p.bands.taxable_income, 0)}) sits in the ${p.bands.marginal_band} band → ${pct(p.marginal.income_rate)} relief on pension contributions.` +
    (p.bands.in_pa_taper
      ? `\n\nYou're in the £100,000–£125,140 zone where each £2 also restores £1 of personal allowance, so the effective relief is ~60%.`
      : '')
  return (
    <div className="cards-row">
      <div className="stat-card tip-wrap" data-tip={aniTip}>
        <div className="stat-title">Adjusted net income</div>
        <div className="stat-value">{gbp(p.income.adjusted_net_income, 0)}</div>
        <div className="muted small">
          marginal band: {p.bands.marginal_band}
          {p.bands.in_pa_taper && ' · in the 60% zone'}
        </div>
      </div>
      <div className="stat-card tip-wrap" data-tip={paTip}>
        <div className="stat-title">Personal allowance</div>
        <div className="stat-value">{gbp(p.allowances.personal_allowance, 0)}</div>
        <div className="muted small">{p.bands.in_pa_taper ? 'tapered' : 'full allowance'}</div>
      </div>
      <div className="stat-card tip-wrap" data-tip={taxTip}>
        <div className="stat-title">Est. tax on investments</div>
        <div className="stat-value">
          {gbp(p.tax.dividend_tax + p.tax.savings_tax + p.tax.cgt_estimate)}
        </div>
        <div className="muted small">
          dividends {gbp(p.tax.dividend_tax, 0)} · interest {gbp(p.tax.savings_tax, 0)} · CGT{' '}
          {gbp(p.tax.cgt_estimate, 0)}
        </div>
      </div>
      <div className="stat-card tip-wrap" data-tip={marginalTip}>
        <div className="stat-title">Marginal relief rate</div>
        <div className="stat-value">{pct(p.marginal.effective_rate)}</div>
        <div className="muted small">what £1 of pension contribution saves</div>
      </div>
      <p className="muted small" style={{ gridColumn: '1 / -1', margin: 0 }}>
        Hover any card to see exactly how it was computed.
      </p>
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
