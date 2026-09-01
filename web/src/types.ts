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
  // Past this many pending requests the login page stops accepting new ones.
  pending_limit?: number
}

// Mirrors core.repo.ACCOUNT_TYPES.
export type AccountType =
  | 'schwab_individual'
  | 'schwab_awards'
  | 'freetrade_gia'
  | 'hl_fund_share'
  | 'interactive_brokers'
  | 'morgan_stanley_awards'
  | 'sharesight'
  | 'trading212_invest'
  | 'vanguard_gia'
  | 'bank_generic'
  | 'raw_csv'

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

// One line of the cash ledger the balance check prints when it fails; `note`
// stands in for the "N earlier transactions omitted" marker.
export interface BalanceLedgerRow {
  date?: string | null
  action?: string | null
  symbol?: string | null
  description?: string | null
  amount?: string | null
  balance?: string | null
  note?: string
}

export interface CalcError {
  type: string
  message: string
  symbol?: string
  // The offending row, for InvalidTransactionError and its subclasses.
  transaction?: ErrorTransaction
  // negative_balance only.
  broker?: string
  currency?: string
  balance?: string
  ledger?: BalanceLedgerRow[]
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
  /** A gilt or UK T-bill: listed, but exempt from CGT (TCGA 1992 s115). */
  exempt?: boolean
}

export interface OtherIncomeRow {
  date: string
  /** Ticker of the REIT, or the broker for a share-lending fee. */
  source: string
  amount_gbp: string
  tax_gbp: string
}

export interface ExemptSecurity {
  symbol: string
  isin: string | null
  kind: 'gilt' | 'tbill' | 'manual'
  title: string | null
  source: 'detected' | 'configured'
}

export interface Dividend {
  date: string
  symbol: string
  /** ISIN country code of the payer; GB = UK dividend, else foreign. */
  country?: string | null
  isin?: string | null
  /** The payment before conversion, and the HMRC monthly rate used. */
  currency?: string | null
  gross?: string | null
  fx_rate?: string | null
  amount_gbp: string
  tax_at_source_gbp: string
  is_interest: boolean
  treaty: { country: string; relief_gbp: string } | null
}

/** How a distribution is taxed once classified, whatever the broker called it. */
export type DistributionKind =
  | 'uk_dividend'
  | 'foreign_dividend'
  | 'property_income_distribution'
  | 'interest_distribution'
  | 'uk_interest'
  | 'foreign_interest'
  | 'share_lending_fee'
  | 'eri_dividend'
  | 'eri_interest'

export interface DistributionRow {
  date: string
  symbol: string | null
  source: string | null
  kind: DistributionKind
  label: string
  taxed_as: 'dividend' | 'savings' | 'property' | 'misc'
  uses_dividend_allowance: boolean
  currency: string | null
  gross: string | null
  fx_rate: string | null
  gross_gbp: number
  withheld_gbp: number
  treaty_relief_gbp: number
  why: string
}

export interface PaymentsOnAccount {
  required: boolean
  threshold: number
  liability_excluding_cgt: number
  over_threshold: boolean
  tax_collected_at_source: number
  percent_at_source: number
  under_80_percent_at_source: boolean
  each_instalment: number
  explain: string
  /** True when no P60 was entered, so PAYE was assumed correct rather than checked. */
  assumed_paye?: boolean
}

/** The mid-year CGT rate change and the box 51 adjustment it forces. */
export interface RateChangeSplit {
  before: number
  after: number
  date: string
  rates_before: { basic: number; higher: number }
  rates_after: { basic: number; higher: number }
  has_pre_change_disposals: boolean
  needs_box_51_adjustment: boolean
  cgt_adjustment: number
  sa_cgt_at_pre_oct_rates: number
  cgt_total: number
  /** True when no planner income was available to place the gains in the bands. */
  estimated: boolean
  note: string
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
  interest_tax?: { date: string; broker: string; currency: string; amount_gbp: string }[]
  other_income?: OtherIncomeRow[]
  exempt?: { securities: ExemptSecurity[]; ais_applies: boolean; ais_nominal_peak: string }
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
    other_income: { value: number; tax_taken_off: number; estimated_tax: number | null }
  }
  sa_boxes: SABox[]
  distributions: DistributionRow[]
  distribution_totals: Record<string, number>
  rate_change_split: RateChangeSplit | null
  exempt_disposals: {
    count: number
    tbill_count: number
    proceeds: number
    gain: number
    symbols: string[]
    explain: string
  } | null
  warnings: string[]
  has_estimates: boolean
  tax_due: TaxDue
}

export interface CgtBucket {
  key: string
  label: string
  gain: number
  relief: number
  net: number
  rounded: number
  at_basic: number
  at_higher: number
  basic_rate: number
  higher_rate: number
  tax: number
}

/** One P60. Pay and tax deducted come off the form; the code only explains. */
export interface EmploymentInput {
  name?: string
  pay?: number
  tax_deducted?: number
  tax_code?: string
  student_loan_deducted?: number
}

/** A line of the Self Assessment bill. They sum to the row keyed "total". */
export interface BillRow {
  key: string
  label: string
  amount: number
  explain: string
  included: boolean
  total?: boolean
}

export interface TaxCodeExplanation {
  code: {
    code: string
    allowance: string | null
    flat_rate: string | null
    describe: string
    usable: boolean
    problem: string | null
  }
  implied_tax: number | null
  actual_tax?: number
  gap?: number
  explains: boolean
  message: string
}

export interface StudentLoan {
  plan: string
  available: boolean
  label?: string
  threshold?: number
  rate?: number
  total_due?: number
  deducted_via_paye?: number
  balance?: number
  explain: string
}

/** The whole bill: investment income plus whatever PAYE got wrong on salary. */
export interface SelfAssessment {
  /** False when no P60 was entered — the headline falls back to investments. */
  reconciled: boolean
  rounding_mode: 'hmrc' | 'exact'
  tax_year: number
  label: string
  due_date: string
  income: Record<string, number>
  allowances: Record<string, number>
  bands: Record<string, number | string>
  income_tax: {
    non_savings: number
    savings: number
    dividends_gross: number
    dividends: number
    total: number
  }
  at_source: {
    paye: number
    other_income: number
    total: number
    employments: {
      name: string
      pay: number
      tax_deducted: number
      student_loan_deducted: number
      tax_code: string | null
    }[]
  }
  ftcr: { total: number; dividends: number; interest: number }
  income_tax_shortfall: number
  employment_shortfall: number
  already_paid: {
    total: number
    payments_on_account_made: number
    tax_paid_on_gains: number
  }
  sa_bill: number
  /** Today's figure: tax on investment income alone. */
  investment_only: number
  investment_only_parts: Record<string, number>
  student_loan: StudentLoan | null
  payments_on_account: PaymentsOnAccount
  tax_code_explanation: TaxCodeExplanation | null
  warnings: string[]
  rows: BillRow[]
}

export interface HistoryYear {
  tax_year: number
  label: string
  due_date: string
  estimate: number
  investment_only: number
  employment_shortfall: number
  reconciled: boolean
  has_report: boolean
  actual: number | null
  difference: number | null
  matches: boolean
}

export interface History {
  years: HistoryYear[]
  explain: string
  unreconciled: number[]
  mismatched: number[]
}

export interface TaxDue {
  available: boolean
  /** The whole bill, PAYE reconciliation included. */
  self_assessment?: SelfAssessment
  total?: number
  /** The bill without capital gains tax — what the payments-on-account test uses. */
  excluding_cgt?: number
  cgt?: number
  cgt_sa_at_pre_oct_rates?: number
  cgt_adjustment?: number
  cgt_note?: string | null
  cgt_buckets?: CgtBucket[]
  dividends?: number
  dividends_before_ftcr?: number
  ftcr?: number
  foreign_tax_withheld?: number
  interest?: number
  other_income?: number
  payments_on_account?: PaymentsOnAccount
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
  // Ordered, concrete steps for claiming the tip; shown when the card is open.
  how_to_execute: string[]
  // A use-it-or-lose-it benefit already gone (red) or about to go (orange).
  status: 'lost' | 'expiring' | null
  status_note: string | null
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
      dividend_tax_before_ftcr: number
      ftcr: number
      /** Same as cgt_total; kept for callers that predate the rate split. */
      cgt_estimate: number
      cgt_total: number
      /** What the SA return's own calculation produces (pre-30-Oct rates). */
      sa_cgt_at_pre_oct_rates: number
      /** SA108 box 51: the extra due on post-30-Oct disposals. */
      cgt_adjustment: number
      cgt_note: string | null
      /** Investment income only — the old headline, now a sub-total. */
      investment_only: number
      /** What the return will actually ask for, PAYE catch-up included. */
      sa_bill: number
      reconciled: boolean
    }
    cgt: {
      total_gain: number
      taxable_gain: number
      cgt_total: number
      sa_cgt_at_pre_oct_rates: number
      cgt_adjustment: number
      split_applies: boolean
      dates_known: boolean
      needs_box_51_adjustment: boolean
      adjustment_note: string | null
      buckets: CgtBucket[]
    }
    payments_on_account: PaymentsOnAccount
    self_assessment: SelfAssessment
    marginal: { income_rate: number; effective_rate: number }
  }
  tips: Tip[]
  filing_deadline: string
  year: {
    cgt_mid_year_change?: { date: string; rates_before: { basic: number; higher: number } }
    personal_allowance: number
    pa_taper_start: number
    /** Income at which the tapered personal allowance reaches nil. */
    pa_taper_end: number
    basic_band: number
    /** Taxable income above which the additional rate starts — £150,000 in
     *  2022/23, £125,140 from 2023/24. */
    higher_rate_limit: number
    cgt_allowance: number
    dividend_allowance: number
    income_rates: Record<string, number>
    dividend_rates: Record<string, number>
    cgt_rates_shares: { basic: number; higher: number }
  }
  /** The whole year table, grouped and sourced, for checking against gov.uk. */
  year_parameters: YearParameterGroup[] | null
}

export interface YearParameterGroup {
  title: string
  /** The gov.uk page these figures were checked against. */
  source: string
  rows: { label: string; value: number | string; kind: 'money' | 'text' }[]
}

export interface MappingNeeded {
  needs_mapping: true
  headers: string[]
  sample: string[][]
}

// ── Where the year stands (GET /api/status/:year) ─────────────────────────────

/** todo = untouched, attention = done but wrong/stale/incomplete, done = settled. */
export type StepState = 'todo' | 'attention' | 'done'

export type StepKey = 'documents' | 'income' | 'report' | 'plan'

export interface Step {
  key: StepKey
  title: string
  state: StepState
  /** One line of state, shown under the step name in the rail. */
  headline: string
  /** Why it matters — the sentence shown when this step is what to do next. */
  detail: string
  /** Label for the button that resolves it, or null when nothing is pending. */
  action: string | null
  /** Report step only: computed from documents that have since changed. */
  stale?: boolean
  /** What moved since the run — named, so the claim can be checked. */
  changes?: string[]
  run_at?: string | null
}

export interface YearStatus {
  tax_year: number
  label: string
  in_progress: boolean
  year_end: string
  filing_deadline: string
  /** What the clock is running towards: acting before 5 Apr, or filing by 31 Jan. */
  deadline: { what: 'act' | 'file'; date: string; days: number }
  steps: Step[]
  /** The earliest unfinished step — the one thing to do now. */
  next: { key: StepKey; title: string; action: string | null; why: string } | null
  bill: {
    reconciled: boolean
    amount: number
    investment_only: number
    due_date: string
  } | null
}
