import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import Section from '../components/Section'
import StepHeader from '../components/StepHeader'
import type { EmploymentInput, StepKey, YearStatus } from '../types'
import { taxYearLabel } from '../utils/format'

type Field = { key: string; label: string; where: string; kind?: 'money' | 'select' }

type Group = {
  id: string
  title: string
  /** What entering this group buys you — the reason to bother with it. */
  why: string
  fields: Field[]
  /** Rendered above the fields (the P60 rows, the carry-forward block). */
  extra?: 'employments' | 'prior-pensions'
}

// Order matters. The P60 comes first because it is the single most
// consequential thing on the page: for an additional-rate salary the PAYE
// shortfall is routinely larger than the whole investment bill, and without it
// nothing else on the page can be priced at the right marginal rate. The old
// form opened with three pension boxes and buried the P60 below them.
const GROUPS = (): Group[] => [
  {
    id: 'employment',
    title: 'Employment & PAYE',
    why: 'Sets your marginal rate and shows what your tax code got wrong on salary. Everything else on this page is priced off it.',
    extra: 'employments',
    fields: [
      {
        key: 'benefits_in_kind',
        label: 'Benefits in kind (P11D)',
        where:
          'P11D → total cash equivalent of benefits (company car, private medical, interest-free loans). Taxable income, and often only partly collected through your tax code, so it usually adds to the shortfall rather than being already paid.',
      },
      {
        key: 'student_loan_plan',
        label: 'Student loan plan',
        kind: 'select',
        where:
          "Which plan you repay, from your annual statement or the Student Loans Company. Repayments are 9% of income over the plan's threshold (6% for a postgraduate loan), and unearned income over £2,000 counts in full — not just the excess.",
      },
    ],
  },
  {
    id: 'pension',
    title: 'Pension contributions',
    why: 'Drives the annual allowance, the carry-forward you still have, and what a further £1 of contribution would save you.',
    extra: 'prior-pensions',
    fields: [
      {
        key: 'pension_employee',
        label: 'Via payroll — yours',
        where:
          'Your own contributions deducted through salary this tax year, additional voluntary contributions (AVCs) included: final March payslip → “Pension YTD” (often labelled “EEs Pension” or “AE Pension EE”), or your workplace pension’s annual statement. Payslips show it as a negative deduction — enter it as a positive number, without the “-”. Treated as salary sacrifice: it counts as an employer contribution for the annual allowance and is added back to threshold income for the taper test.',
      },
      {
        key: 'pension_employer',
        label: 'Via payroll — employer',
        where:
          'Employer contributions this tax year: final March payslip → “Employer pension YTD” (often labelled “ERs Pension” or “AE Pension ER”), or the workplace pension’s annual statement. Enter as a positive number. Counts towards the annual allowance (£60,000 since 2023/24, £40,000 before; tapered when adjusted income is over £260,000).',
      },
      {
        key: 'sipp_paid',
        label: 'SIPP paid personally (net)',
        where:
          'What you actually transferred into a personal pension, SIPP or standalone AVC contract this tax year — the provider’s contribution history. Enter the net amount; HMRC adds 25% on top automatically.',
      },
    ],
  },
  {
    id: 'other-income',
    title: 'Other income & allowances',
    why: 'Anything HMRC taxes that no broker export covers. Left out, the bill reads low and the tips are priced in the wrong band.',
    fields: [
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
        key: 'self_employment_income',
        label: 'Self-employment / other untaxed income',
        where:
          'Any income with no tax taken off it — freelancing, a side business, untaxed rent. This app does NOT compute tax or Class 2/4 National Insurance on it; it asks so the estimate can warn you that it is incomplete rather than quietly leaving it out.',
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
    ],
  },
  {
    id: 'payments',
    title: 'Payments & adjustments',
    why: 'What you have already handed HMRC for this year, and how the figures should be rounded. Comes straight off the bill.',
    fields: [
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
        key: 'rounding_mode',
        label: 'Rounding',
        kind: 'select',
        where:
          'HMRC rounds each income source down to the whole pound and each loss up before charging tax, which is how the real bill is worked out — keep it on HMRC rounding to match. Pence-precise shows what the bill would be without that rounding.',
      },
    ],
  },
]

// Prior-year pension totals: needed only for carry-forward, and only when that
// year's own Planner is empty. Folded away by default — three boxes about years
// you are not looking at should not be the second thing on the page.
const PRIOR_PENSION_FIELDS = (year: number): Field[] => [
  {
    key: 'pension_prior_1',
    label: `Pension total, ${taxYearLabel(year - 1)}`,
    where: `ALL contributions (yours + employer + AVCs + SIPP gross) in the ${taxYearLabel(year - 1)} tax year (6 Apr ${year - 1} – 5 Apr ${year}). Sum the contribution rows between those dates in your pension provider's transaction history — transfers in don't count. Needed for carry-forward. Leave blank to use that year's own Income page instead. Enter that year's income in its own page so its taper can be checked — otherwise its carry-forward is flagged as unverified.`,
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

const SELECT_OPTIONS: Record<string, { value: string; label: string }[]> = {
  student_loan_plan: [
    { value: '', label: 'None' },
    { value: 'plan_1', label: 'Plan 1' },
    { value: 'plan_2', label: 'Plan 2' },
    { value: 'plan_4', label: 'Plan 4 (Scotland)' },
    { value: 'plan_5', label: 'Plan 5' },
    { value: 'postgraduate', label: 'Postgraduate loan' },
  ],
  rounding_mode: [
    { value: 'hmrc', label: 'HMRC rounding (matches the real bill)' },
    { value: 'exact', label: 'Pence-precise' },
  ],
}

// Saved inputs are all numbers except these, which are text HMRC issued or a
// choice from a list. Everything else is parsed as a number on the way out.
const TEXT_INPUTS = new Set(['student_loan_plan', 'rounding_mode'])
const EMPLOYMENTS_KEY = 'employments'

type SavedInputs = Record<string, unknown>

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

/** Everything the calculator cannot read from a broker export.
 *
 *  Split out of the old Planner, which was a twenty-field data-entry form with
 *  the advice it produced hidden underneath it. Inputs belong on an input page;
 *  what they produce belongs on the Report and the Plan. */
export default function IncomeView({
  year,
  status,
  onChange,
  onGoTo,
}: {
  year: number
  status: YearStatus | null
  onChange: () => void
  onGoTo: (key: StepKey) => void
}) {
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [employments, setEmployments] = useState<EmploymentInput[]>([])
  const [saved, setSaved] = useState<{ inputs: Record<string, string>; rows: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setSaved(null)
    api.get<SavedInputs | null>(`/api/planner/${year}/inputs`).then((data) => {
      const asStrings: Record<string, string> = {}
      for (const [k, v] of Object.entries(data ?? {})) {
        if (k !== EMPLOYMENTS_KEY) asStrings[k] = String(v)
      }
      const rows = (data ?? {})[EMPLOYMENTS_KEY]
      const list = Array.isArray(rows) ? (rows as EmploymentInput[]) : []
      setInputs(asStrings)
      setEmployments(list)
      setSaved({ inputs: asStrings, rows: JSON.stringify(list) })
    })
  }, [year])

  // Nothing here is computed until it is saved, so an unsaved edit has to look
  // unsaved — a page that silently holds your P60 while the bill still says
  // "no P60 entered" is the worst of both.
  const dirty = useMemo(() => {
    if (!saved) return false
    if (JSON.stringify(employments) !== saved.rows) return true
    const keys = new Set([...Object.keys(inputs), ...Object.keys(saved.inputs)])
    for (const k of keys) {
      if ((inputs[k] ?? '') !== (saved.inputs[k] ?? '')) return true
    }
    return false
  }, [inputs, employments, saved])

  const set = useCallback((key: string, value: string) => {
    setJustSaved(false)
    setInputs((prev) => ({ ...prev, [key]: value }))
  }, [])

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
      const asStrings: Record<string, string> = {}
      for (const [k, v] of Object.entries(inputs)) if (v !== '') asStrings[k] = v
      setSaved({ inputs: asStrings, rows: JSON.stringify(rows) })
      setEmployments(rows)
      setJustSaved(true)
      onChange()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const groups = GROUPS()

  return (
    <div>
      <StepHeader
        step="income"
        status={status}
        title={`Income ${taxYearLabel(year)}`}
        onGoTo={onGoTo}
      />

      <p className="muted small">
        All figures for this tax year (6 Apr – 5 Apr). Hover the <i className="info-icon">i</i> on
        any field to see which document it comes from. Nothing is computed until you save.
      </p>

      {groups.map((group, i) => (
        <Section
          key={group.id}
          id={`income-${group.id}`}
          title={
            <>
              <span className="group-index">{i + 1}</span>
              {group.title}
            </>
          }
          defaultOpen
        >
          <p className="muted small group-why">{group.why}</p>

          {group.extra === 'employments' && (
            <EmploymentSection
              employments={employments}
              onChange={(rows) => {
                setJustSaved(false)
                setEmployments(rows)
              }}
            />
          )}

          <div className="planner-grid">
            {group.fields.map((f) => (
              <label key={f.key}>
                <InfoLabel label={f.label} where={f.where} />
                {f.kind === 'select' ? (
                  <select
                    value={inputs[f.key] ?? (f.key === 'rounding_mode' ? 'hmrc' : '')}
                    onChange={(e) => set(f.key, e.target.value)}
                  >
                    {SELECT_OPTIONS[f.key].map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    inputMode="decimal"
                    placeholder="0"
                    value={inputs[f.key] ?? ''}
                    onChange={(e) => set(f.key, e.target.value)}
                  />
                )}
              </label>
            ))}
          </div>

          {group.extra === 'prior-pensions' && (
            <Section
              id="income-prior-pensions"
              title="Earlier years, for carry-forward"
              meta="only needed when those years' own pages are empty"
              defaultOpen={false}
            >
              <div className="planner-grid">
                {PRIOR_PENSION_FIELDS(year).map((f) => (
                  <label key={f.key}>
                    <InfoLabel label={f.label} where={f.where} />
                    <input
                      type="number"
                      inputMode="decimal"
                      placeholder="0"
                      value={inputs[f.key] ?? ''}
                      onChange={(e) => set(f.key, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            </Section>
          )}
        </Section>
      ))}

      <div className={dirty ? 'save-bar dirty' : 'save-bar'}>
        <span className="save-state">
          {dirty
            ? 'Unsaved changes — nothing is recomputed until you save'
            : justSaved
              ? 'Saved. The Report and Plan now use these figures.'
              : 'All changes saved'}
        </span>
        <div className="save-actions">
          {error && <span className="error-text">{error}</span>}
          <button className="btn primary" disabled={saving || !dirty} onClick={save}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          {!dirty && (
            <button className="btn" onClick={() => onGoTo(status?.next?.key ?? 'report')}>
              {status?.next && status.next.key !== 'income'
                ? (status.next.action ?? `Go to ${status.next.title}`)
                : 'See the report'}
            </button>
          )}
        </div>
      </div>
    </div>
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
    onChange(rows.map((r, j) => (j === i ? { ...r, [key]: value === '' ? undefined : value } : r)))
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
