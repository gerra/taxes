import type { SelfAssessment } from '../../types'

/** An empty Self Assessment computation: nothing entered, nothing owed.
 * Tests spread over it and set only the fields they are about. */
export function emptySelfAssessment(over: Partial<SelfAssessment> = {}): SelfAssessment {
  return {
    reconciled: false,
    rounding_mode: 'hmrc',
    tax_year: 2025,
    label: '2025/26',
    due_date: '2027-01-31',
    income: {},
    allowances: {},
    bands: {},
    income_tax: { non_savings: 0, savings: 0, dividends_gross: 0, dividends: 0, total: 0 },
    at_source: { paye: 0, other_income: 0, total: 0, employments: [] },
    ftcr: { total: 0, dividends: 0, interest: 0 },
    income_tax_shortfall: 0,
    employment_shortfall: 0,
    already_paid: { total: 0, payments_on_account_made: 0, tax_paid_on_gains: 0 },
    sa_bill: 0,
    investment_only: 0,
    investment_only_parts: {},
    student_loan: null,
    payments_on_account: {
      required: false,
      threshold: 1000,
      liability_excluding_cgt: 0,
      over_threshold: false,
      tax_collected_at_source: 0,
      percent_at_source: 100,
      under_80_percent_at_source: false,
      each_instalment: 0,
      explain: 'Neither instalment applies.',
    },
    tax_code_explanation: null,
    warnings: [],
    rows: [],
    ...over,
  }
}
