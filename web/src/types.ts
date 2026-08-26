export interface User {
  id: number
  email: string
  name: string
  is_admin: boolean
  pending_requests?: number // admin only
}

// What a not-yet-allowed visitor sees on the login page (GET /api/access/me).
export interface AccessStatus {
  email: string
  name: string
  status: 'pending' | 'approved' | 'declined'
  note: string
}

// Admin panel rows (GET /api/admin/access). Timestamps are SQLite UTC strings.
export interface AccessRequest {
  email: string
  name: string
  status: 'pending' | 'approved' | 'declined'
  note: string
  attempts: number
  first_seen: string
  last_seen: string
  decided_at: string | null
}

export interface AllowedEmail {
  email: string
  name: string
  note: string | null
  decided_at: string | null
  first_seen: string | null
  user_since: string | null
  last_login_at: string | null
  admin: boolean
}

export interface AccessLists {
  pending: AccessRequest[]
  allowed: AllowedEmail[]
  declined: AccessRequest[]
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

export interface ConfirmedEmpty extends DateRange {
  id: number
  note: string
}

export interface AccountCoverage {
  account: Account
  documents: Doc[]
  required: DateRange
  covered: DateRange[]
  confirmed_empty: ConfirmedEmpty[]
  gaps: DateRange[]
  soft_gaps: DateRange[]
  status: 'ok' | 'gaps' | 'missing'
  instructions: string
}

export interface ChecklistNeed {
  type: AccountType
  because: string
  instructions: string
}

export interface Checklist {
  tax_year: number
  label: string
  year_start: string
  year_end: string
  filing_deadline: string
  accounts: AccountCoverage[]
  needs: ChecklistNeed[]
  overall: 'ok' | 'gaps' | 'missing' | 'no_accounts'
}

export interface ErrorTransaction {
  date: string
  action: string
  symbol: string | null
  isin: string | null
  description: string
  quantity: string | null
  price: string | null
  fees: string | null
  amount: string | null
  currency: string
  broker: string
}

export interface CalcError {
  type: string
  message: string
  symbol?: string
  // The offending row, for InvalidTransactionError and its subclasses.
  transaction?: ErrorTransaction
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

export interface VerificationCheck {
  label: string
  status: 'ok' | 'fail' | 'warn' | 'info' | 'pending'
  detail?: string
}

export interface NoticeResolution {
  note: string
  data: Record<string, string>
  evidence_name: string | null
  created_at: string
  status: 'verified' | 'mismatch' | 'partial'
  checks: VerificationCheck[]
  missing: string[]
  verified: boolean | null
  check: string | null
}

export interface VerificationField {
  key: string
  label: string
  type: 'money' | 'date' | 'choice' | 'checkbox' | 'text'
  required?: boolean
  options?: { value: string; label: string }[]
}

export interface Verification {
  intro: string
  docs: { title: string; where: string }[]
  fields: VerificationField[]
}

export interface Notice {
  key: string
  /** Tax year a dated notice belongs to; null = about the run as a whole. */
  tax_year?: number | null
  data?: Record<string, string>
  verification?: Verification
  resolution?: NoticeResolution | null
  kind: 'info' | 'warning' | 'error'
  category: string
  title: string
  summary: string
  occurrences: string[]
  why: string | null
  action: string | null
  count: number
  raw: string[]
}

export interface ReportView {
  tax_year: number
  label: string
  filing_deadline: string
  notices: Notice[]
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
  tax_due: TaxDue
}

export interface TaxDue {
  available: boolean
  total?: number
  cgt?: number
  dividends?: number
  interest?: number
  marginal_band?: string
  personal_allowance?: number
  psa?: number
  cgt_at_basic?: number
  cgt_at_higher?: number
  cgt_rates?: { basic: number; higher: number } | null
  dividend_allowance?: number | null
  cgt_allowance?: number | null
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
  // "How it was computed": one line per step, shown when the card is expanded.
  detail: string | null
  // Gaps in the inputs the figure relies on (e.g. a prior year with no income).
  warnings: string[]
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
  year: {
    personal_allowance: number
    pa_taper_start: number
    basic_band: number
    additional_threshold: number
    cgt_allowance: number
    dividend_allowance: number
    income_rates: Record<string, number>
    dividend_rates: Record<string, number>
    cgt_rates_shares: { basic: number; higher: number }
  }
}

export interface MappingNeeded {
  needs_mapping: true
  headers: string[]
  sample: string[][]
}
