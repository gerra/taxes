export interface User {
  id: number
  email: string
  name: string
}

export type AccountType =
  'schwab_individual' | 'schwab_awards' | 'freetrade_gia' | 'bank_generic' | 'raw_csv'

export interface Account {
  id: number
  type: AccountType
  name: string
  first_activity_date: string | null
}

export interface Doc {
  id: number
  account_id: number
  filename: string
  size: number
  tx_count: number
  date_min: string | null
  date_max: string | null
  warnings: string[]
  source: string
  uploaded_at: string
}

export interface DateRange {
  start: string
  end: string
}

export interface AccountCoverage {
  account: Account
  documents: Doc[]
  required: DateRange
  covered: DateRange[]
  gaps: DateRange[]
  soft_gaps: DateRange[]
  status: 'ok' | 'gaps' | 'missing'
  instructions: string
}

export interface Checklist {
  tax_year: number
  label: string
  year_start: string
  year_end: string
  filing_deadline: string
  accounts: AccountCoverage[]
  overall: 'ok' | 'gaps' | 'missing' | 'no_accounts'
}

export interface CalcError {
  type: string
  message: string
  symbol?: string
}

export interface CalcRun {
  id: number
  tax_year: number
  status: 'pending' | 'running' | 'ok' | 'error'
  has_pdf: boolean
  error?: CalcError
}

export interface Entry {
  rule: string
  quantity: string | null
  amount: string | null
  allowable_cost: string | null
  fees: string | null
  gain: string | null
  new_quantity: string | null
  new_pool_cost: string | null
  bnb_date: string | null
}

export interface DisposalEvent {
  date: string
  symbol: string
  entries: Entry[]
  amount: string | null
  gain: string | null
}

export interface Dividend {
  date: string
  symbol: string
  amount_gbp: string
  tax_at_source_gbp: string
  is_interest: boolean
  treaty: { country: string; relief_gbp: string } | null
}

export interface InterestRow {
  date: string
  broker: string
  currency: string
  uk: boolean
  amount_gbp: string
}

export interface Bundle {
  schema_version: number
  tax_year: number
  totals: Record<string, string | number | null>
  disposals: DisposalEvent[]
  acquisitions: DisposalEvent[]
  dividends: Dividend[]
  interest: InterestRow[]
  interest_by_source: { broker: string; currency: string; amount_gbp: string }[]
  eri_distributions: { date: string; symbol: string; amount_gbp: string }[]
  portfolio_eoy: { symbol: string; quantity: string; pool_cost: string }[]
  warnings: string[]
}

export interface SABox {
  form: string
  box: string
  label: string
  value: number
  format?: string
  explain: string
}

export interface ReportView {
  tax_year: number
  label: string
  filing_deadline: string
  cards: {
    taxable_gain: { value: number | null; sub?: string | null; estimated_tax: number | null }
    dividends_taxable: { value: number; sub?: string; estimated_tax: number | null }
    uk_interest: { value: number }
    foreign_interest: { value: number }
    interest_estimated_tax: number | null
  }
  sa_boxes: SABox[]
  rate_change_split: { before: number; after: number; date: string } | null
  warnings: string[]
  has_estimates: boolean
}

export interface Report {
  status: string
  run_id: number
  has_pdf: boolean
  provisional: boolean
  coverage_overall: string
  view: ReportView
  bundle: Bundle
}

export interface Tip {
  id: string
  title: string
  what_to_do: string
  why: string
  estimated_win_gbp: number | null
  deadline: string | null
  confidence: string
}

export interface PlannerData {
  tax_year: number
  label: string
  has_report: boolean
  invest: Record<string, number>
  profile: {
    income: Record<string, number>
    allowances: Record<string, number>
    bands: {
      basic_top: number
      additional_top: number
      taxable_income: number
      marginal_band: string
      in_pa_taper: boolean
    }
    tax: {
      income_tax_total: number
      savings_tax: number
      dividend_tax: number
      cgt_estimate: number
      cgt_note: string | null
    }
    marginal: { income_rate: number; effective_rate: number }
  }
  tips: Tip[]
  filing_deadline: string
}

export interface MappingNeeded {
  needs_mapping: true
  headers: string[]
  sample: string[][]
}
