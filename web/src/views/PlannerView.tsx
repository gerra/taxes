import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { EmploymentInput, PlannerData, SelfAssessment, Tip } from '../types'
import { currentTaxYear, gbp, pct, shortDate, taxYearLabel } from '../utils/format'

// Input fields for the planner; prior-year pension rows are named after the
// actual tax years so they match a provider's statement.
//
// Employment pay and tax deducted are NOT here — they live in the P60 section
// below, one row per employment, because the pair has to be entered together:
// pay without the tax deducted cannot be reconciled, and this app must never
// guess at the tax.
const fields = (year: number): { key: string; label: string; where: string }[] => [
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
      'Your own contributions deducted through salary this tax year, additional voluntary contributions (AVCs) included: final March payslip → “Pension YTD” (often labelled “EEs Pension” or “AE Pension EE”), or your workplace pension’s annual statement. Payslips show it as a negative deduction — enter it as a positive number, without the “-”. Treated as salary sacrifice: it counts as an employer contribution for the annual allowance and is added back to threshold income for the taper test.',
  },
  {
    key: 'pension_employer',
    label: 'Pension via payroll — employer',
    where:
      'Employer contributions this tax year: final March payslip → “Employer pension YTD” (often labelled “ERs Pension” or “AE Pension ER”), or the workplace pension’s annual statement. Enter as a positive number. Counts towards the annual allowance (£60,000 since 2023/24, £40,000 before; tapered when adjusted income is over £260,000).',
  },
  {
    key: 'sipp_paid',
    label: 'SIPP paid personally (net)',
    where:
      'What you actually transferred into a personal pension, SIPP or standalone AVC contract this tax year — the provider’s contribution history. Enter the net amount; HMRC adds 25% on top automatically.',
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
    where: `ALL contributions (yours + employer + AVCs + SIPP gross) in the ${taxYearLabel(year - 1)} tax year (6 Apr ${year - 1} – 5 Apr ${year}). Sum the contribution rows between those dates in your pension provider's transaction history — transfers in don't count. Needed for carry-forward. Leave blank to use that year's own Planner pension fields instead. Enter that year's income in its own Planner so its taper can be checked — otherwise its carry-forward is flagged as unverified.`,
  },
  {
    key: 'pension_prior_2',
    label: `Pension total, ${taxYearLabel(year - 2)}`,
    where: `Same for 6 Apr ${year - 2} – 5 Apr ${year - 1}. Unused allowance from this year can be carried forward; same fallback and income rules as above.`,
  },
  {
    key: 'pension_prior_3',
    label: `Pension total, ${taxYearLabel(year - 3)}`,
    where: `Same for 6 Apr ${year - 3} – 5 Apr ${year - 2} — the oldest year carry-forward can reach.`,
  },
]

// The employment / PAYE section. Optional as a whole: skip it and the estimate
// falls back to investment income alone with a visible caveat. Enter it and the
// tool can see what PAYE actually collected, which for a high earner is usually
// where the bill really comes from.
//
// Pay and tax deducted are required together. The rest are optional and each
// says why it matters, because "leave it blank" is only safe advice when you
// know what blank costs you.
const EMPLOYMENT_FIELDS: {
  key: keyof EmploymentInput
  label: string
  type: 'money' | 'text'
  required?: boolean
  where: string
}[] = [
  {
    key: 'name',
    label: 'Employer',
    type: 'text',
    where: 'Just a label so you can tell two P60s apart. Not used in any calculation.',
  },
  {
    key: 'pay',
    label: 'Total pay for the year (P60)',
    type: 'money',
    required: true,
    where:
      'P60 → “Pay” in the “Pay and Income Tax details” box, the “In this employment / Total for year” figure. This is already net of any net-pay or salary-sacrifice pension.',
  },
  {
    key: 'tax_deducted',
    label: 'Total tax deducted (P60)',
    type: 'money',
    required: true,
    where:
      'P60 → “Tax deducted” next to the pay figure. Enter exactly what the P60 says. This app never works it out from your tax code: the code is what HMRC asked your employer to take, and this is what it actually took — the gap between them is the whole point.',
  },
  {
    key: 'tax_code',
    label: 'Final tax code (P60)',
    type: 'text',
    where:
      'P60 → “Final tax code”. Used only to EXPLAIN a shortfall, never to compute one. A code like 151T grants £1,519 of allowance; if you were not entitled to it, re-running PAYE with it shows the shortfall was the code’s fault rather than something you have missed. Also the only cross-check on a mistyped “tax deducted”.',
  },
  {
    key: 'student_loan_deducted',
    label: 'Student loan deducted (P60)',
    type: 'money',
    where:
      'P60 → “Student Loan deductions”. Whatever payroll already collected comes off the repayment worked out below, so leaving it blank overstates what you still owe.',
  },
]

// Scalar fields that belong with the employment section rather than with
// income and contributions.
const PAYE_FIELDS: { key: string; label: string; where: string }[] = [
  {
    key: 'benefits_in_kind',
    label: 'Benefits in kind (P11D)',
    where:
      'P11D → total cash equivalent of benefits (company car, private medical, interest-free loans). Taxable income, and often only partly collected through your tax code, so it usually adds to the shortfall rather than being already paid.',
  },
  {
    key: 'self_employment_income',
    label: 'Self-employment / other untaxed income',
    where:
      'Any income with no tax taken off it — freelancing, a side business, untaxed rent. This app does NOT compute tax or Class 2/4 National Insurance on it; it asks so the estimate can warn you that it is incomplete rather than quietly leaving it out.',
  },
  {
    key: 'payments_on_account_made',
    label: 'Payments on account already made',
    where:
      'What you have already paid towards this year, usually two instalments on 31 Jan and 31 Jul. HMRC → “Your Self Assessment account” → payments. Comes straight off the bill.',
  },
  {
    key: 'tax_paid_on_gains',
    label: 'Tax already paid on gains (real-time service)',
    where:
      'ONLY if you actually paid capital gains tax through HMRC’s “report and pay CGT” real-time service. Do not enter the taxable gain here — this box is a tax figure, and HMRC will credit whatever you type as tax already paid.',
  },
  {
    key: 'entered_losses',
    label: 'Losses as you will enter them on the return',
    where:
      'Optional check. Type the loss figure you are about to put in SA108 box 27 and this will tell you if you have rounded it the wrong way — HMRC rounds losses UP to the whole pound, in your favour.',
  },
  {
    key: 'actual_tax_paid',
    label: 'What HMRC actually charged for this year',
    where:
      'Filled in after the event, from your HMRC statement. Not used in any calculation — it drives the History tab, which compares this tool’s estimate against what you really paid so a gap in either direction shows up.',
  },
]

const STUDENT_LOAN_PLANS = [
  { value: '', label: 'None' },
  { value: 'plan_1', label: 'Plan 1' },
  { value: 'plan_2', label: 'Plan 2' },
  { value: 'plan_4', label: 'Plan 4 (Scotland)' },
  { value: 'plan_5', label: 'Plan 5' },
  { value: 'postgraduate', label: 'Postgraduate loan' },
]

function InfoLabel({ label, where }: { label: string; where: string }) {
  return (
    <span className="label-text">
      {label}
      <i className="info-icon tip-wrap" data-tip={where} aria-label="Where to find this">
        i
      </i>
    </span>
  )
}

function EmploymentSection({
  employments,
  onChange,
}: {
  employments: EmploymentInput[]
  onChange: (rows: EmploymentInput[]) => void
}) {
  const rows = employments.length > 0 ? employments : [{}]
  const update = (i: number, key: keyof EmploymentInput, value: string) => {
    const next = rows.map((r, j) =>
      j === i ? { ...r, [key]: value === '' ? undefined : value } : r,
    )
    onChange(next)
  }
  return (
    <>
      {rows.map((row, i) => (
        <div key={i} className="employment-row">
          <div className="employment-head">
            <b>{rows.length > 1 ? `P60 ${i + 1}` : 'P60'}</b>
            {rows.length > 1 && (
              <button
                className="link"
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
                title="Remove this employment"
              >
                remove
              </button>
            )}
          </div>
          <div className="planner-grid">
            {EMPLOYMENT_FIELDS.map((f) => (
              <label key={f.key}>
                <InfoLabel label={f.label + (f.required ? ' *' : '')} where={f.where} />
                <input
                  type={f.type === 'money' ? 'number' : 'text'}
                  inputMode={f.type === 'money' ? 'decimal' : undefined}
                  min={f.type === 'money' ? '0' : undefined}
                  placeholder={f.type === 'money' ? '0' : f.key === 'tax_code' ? 'e.g. 1257L' : ''}
                  value={(row[f.key] as string | number | undefined) ?? ''}
                  onChange={(e) => update(i, f.key, e.target.value)}
                />
              </label>
            ))}
          </div>
        </div>
      ))}
      <div className="card-actions">
        <button className="link" onClick={() => onChange([...rows, {}])}>
          + Add another employment
        </button>
      </div>
    </>
  )
}

/** The bill, its breakdown, and everything the tool wants to warn you about. */
function BillSummary({ sa }: { sa: SelfAssessment }) {
  return (
    <section className="card">
      <h3>Estimated Self Assessment bill</h3>
      <div className="bill-headline">
        <div>
          <div className="stat-title">
            {sa.reconciled ? `Bill for ${sa.label}` : `Investment income only, ${sa.label}`}
          </div>
          <div className="stat-value">{gbp(sa.reconciled ? sa.sa_bill : sa.investment_only)}</div>
          <div className="muted small">due {shortDate(sa.due_date)}</div>
        </div>
        {sa.reconciled && (
          <div className="muted small bill-subtotal">
            Investment income alone: <b>{gbp(sa.investment_only)}</b>
            <br />
            The difference is PAYE catch-up on your salary.
          </div>
        )}
      </div>
      <table className="sa-table">
        <tbody>
          {sa.rows.map((r) => (
            <tr key={r.key} className={r.total ? 'bill-total' : undefined}>
              <td>{r.label}</td>
              <td className="num">
                <b>{gbp(r.amount)}</b>
              </td>
              <td className="muted small">{r.explain}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sa.tax_code_explanation && (
        <p className={sa.tax_code_explanation.explains ? 'bill-explained' : 'bill-unexplained'}>
          {sa.tax_code_explanation.message}
        </p>
      )}
      {sa.student_loan && <p className="muted small">{sa.student_loan.explain}</p>}
      {sa.warnings.map((w) => (
        <div key={w} className="banner warn">
          {w}
        </div>
      ))}
    </section>
  )
}

// Saved inputs are all numbers except these, which are text HMRC issued or a
// choice from a list. Everything else is parsed as a number on the way out.
const TEXT_INPUTS = new Set(['student_loan_plan', 'rounding_mode'])
// Stored as a list of objects rather than a scalar, so it is kept apart from
// the flat form state and sent through untouched.
const EMPLOYMENTS_KEY = 'employments'

type SavedInputs = Record<string, unknown>

export default function PlannerView({ year }: { year: number }) {
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [employments, setEmployments] = useState<EmploymentInput[]>([])
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
    api.get<SavedInputs | null>(`/api/planner/${year}/inputs`).then((saved) => {
      const asStrings: Record<string, string> = {}
      for (const [k, v] of Object.entries(saved ?? {})) {
        if (k !== EMPLOYMENTS_KEY) asStrings[k] = String(v)
      }
      setInputs(asStrings)
      const rows = (saved ?? {})[EMPLOYMENTS_KEY]
      setEmployments(Array.isArray(rows) ? (rows as EmploymentInput[]) : [])
      loadPlanner()
    })
  }, [year, loadPlanner])

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const body: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(inputs)) {
        if (v === '') continue
        body[k] = TEXT_INPUTS.has(k) ? v : parseFloat(v)
      }
      // Rows the user added but never filled in are dropped rather than saved
      // as a job that paid nothing.
      const rows = employments
        .map((r) => {
          const clean: EmploymentInput = {}
          if (r.name) clean.name = String(r.name)
          if (r.tax_code) clean.tax_code = String(r.tax_code)
          for (const k of ['pay', 'tax_deducted', 'student_loan_deducted'] as const) {
            const value = r[k]
            if (value !== undefined && value !== null && String(value) !== '') {
              clean[k] = parseFloat(String(value))
            }
          }
          return clean
        })
        .filter((r) => Object.keys(r).length > 0)
      if (rows.length > 0) body[EMPLOYMENTS_KEY] = rows
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
              <InfoLabel label={f.label} where={f.where} />
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
      </section>

      <section className="card">
        <h3>Employment & PAYE</h3>
        <p className="muted small">
          Optional — but without it the estimate can only cover investment income, and for an
          additional-rate salary the PAYE shortfall is routinely the larger half of the bill. Pay
          and tax deducted come straight off the P60; the tax code is used only to explain a gap,
          never to work one out.
        </p>
        <EmploymentSection employments={employments} onChange={setEmployments} />
        <div className="planner-grid">
          {PAYE_FIELDS.map((f) => (
            <label key={f.key}>
              <InfoLabel label={f.label} where={f.where} />
              <input
                type="number"
                inputMode="decimal"
                placeholder="0"
                value={inputs[f.key] ?? ''}
                onChange={(e) => setInputs({ ...inputs, [f.key]: e.target.value })}
              />
            </label>
          ))}
          <label>
            <InfoLabel
              label="Student loan plan"
              where="Which plan you repay, from your annual statement or the Student Loans Company. Repayments are 9% of income over the plan's threshold (6% for a postgraduate loan), and unearned income over £2,000 counts in full — not just the excess."
            />
            <select
              value={inputs.student_loan_plan ?? ''}
              onChange={(e) => setInputs({ ...inputs, student_loan_plan: e.target.value })}
            >
              {STUDENT_LOAN_PLANS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <InfoLabel
              label="Rounding"
              where="HMRC rounds each income source down to the whole pound and each loss up before charging tax, which is how the real bill is worked out — keep it on HMRC rounding to match. Pence-precise shows what the bill would be without that rounding."
            />
            <select
              value={inputs.rounding_mode ?? 'hmrc'}
              onChange={(e) => setInputs({ ...inputs, rounding_mode: e.target.value })}
            >
              <option value="hmrc">HMRC rounding (matches the real bill)</option>
              <option value="exact">Pence-precise</option>
            </select>
          </label>
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
          {year === currentTaxYear() ? (
            <div className="banner info">
              {taxYearLabel(year)} is still running: everything below is still yours to take.
              Allowances that go unused by 5 April {year + 1} don't carry forward.
            </div>
          ) : (
            <div className="banner info">
              {taxYearLabel(year)} has closed — this is the record of what was and wasn't used.
              Switch to {taxYearLabel(currentTaxYear())} for what you can still act on.
            </div>
          )}
          {!data.has_report && (
            <div className="banner info">
              No calculation for this year yet — investment figures are treated as zero. Run the
              Report tab first for accurate tips.
            </div>
          )}
          <BillSummary sa={data.profile.self_assessment} />
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
    `CGT: ${gbp(p.tax.cgt_total)} after the ${gbp(y.cgt_allowance, 0)} annual exempt amount, ` +
    // A year whose rates changed mid-year has a slice at each rate; naming one
    // pair of rates would be wrong for half the disposals.
    (p.cgt.buckets.length > 0
      ? p.cgt.buckets
          .map(
            (b) =>
              `${b.label.toLowerCase()}: ${gbp(b.net)} at ${pct(b.basic_rate)}/${pct(b.higher_rate)}`,
          )
          .join('; ')
      : `${pct(y.cgt_rates_shares.basic)} within the basic band, ${pct(y.cgt_rates_shares.higher)} above`) +
    `.\n` +
    (p.tax.cgt_note ? `${p.tax.cgt_note}\n` : '') +
    `\n` +
    (p.tax.reconciled
      ? `This card is investment income only. Your P60 figures are entered, so the bill above adds ${gbp(p.tax.sa_bill - p.tax.investment_only)} of PAYE catch-up on salary to it.`
      : `This card is investment income only, and assumes employment tax was collected correctly via PAYE. Enter your P60 in the Employment & PAYE section to find out whether it was.`)
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
          {gbp(p.tax.dividend_tax + p.tax.savings_tax + p.tax.cgt_total)}
        </div>
        <div className="muted small">
          dividends {gbp(p.tax.dividend_tax, 0)} · interest {gbp(p.tax.savings_tax, 0)} · CGT{' '}
          {gbp(p.tax.cgt_total, 0)}
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

// A benefit that is gone reads red; one still saveable but on a clock reads orange.
const STATUS_BADGE = {
  lost: { cls: 'bad', label: 'benefit lost' },
  expiring: { cls: 'warn', label: 'expiring' },
} as const

function TipCard({ tip }: { tip: Tip }) {
  const [open, setOpen] = useState(false)
  const badge = tip.status ? STATUS_BADGE[tip.status] : null
  return (
    <section
      className={`card tip-card ${tip.status ? `tip-${tip.status}` : ''} ${open ? 'open' : ''}`}
      onClick={() => setOpen(!open)}
    >
      <div className="card-head">
        <b>{tip.title}</b>
        <span className="tip-badges">
          {badge && <span className={`badge ${badge.cls}`}>{badge.label}</span>}
          {tip.estimated_win_gbp != null && (
            <span className="badge ok">save ~{gbp(tip.estimated_win_gbp, 0)}</span>
          )}
        </span>
      </div>
      {tip.status_note && <p className={`tip-status ${tip.status}`}>{tip.status_note}</p>}
      <p>{tip.what_to_do}</p>
      {tip.warnings.length > 0 && (
        <ul className="tip-warnings">
          {tip.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {open && (
        <>
          <p className="muted">{tip.why}</p>
          {tip.how_to_execute.length > 0 && (
            <>
              <p className="tip-steps-head">How to do it</p>
              <ol className="tip-steps">
                {tip.how_to_execute.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </>
          )}
          {tip.detail && <pre className="tip-detail">{tip.detail}</pre>}
          {tip.deadline && <p className="muted small">Deadline: {shortDate(tip.deadline)}</p>}
        </>
      )}
    </section>
  )
}
