import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { PlannerData, Tip } from '../types'
import { emptySelfAssessment } from './fixtures/self-assessment'
import PlannerView from '../views/PlannerView'

const tip = (over: Partial<Tip>): Tip => ({
  id: 'x',
  title: 'A tip',
  what_to_do: 'do the thing',
  why: 'because',
  estimated_win_gbp: null,
  deadline: null,
  confidence: 'high',
  detail: null,
  warnings: [],
  how_to_execute: [],
  status: null,
  status_note: null,
  ...over,
})

const planner: PlannerData = {
  tax_year: 2025,
  label: '2025/26',
  has_report: true,
  invest: {},
  profile: {
    income: { total: 0, non_savings: 0, savings: 0, dividends: 0, adjusted_net_income: 0 },
    allowances: { personal_allowance: 12570, psa: 500, starting_rate_used: 0 },
    bands: {
      basic_top: 0,
      additional_top: 0,
      taxable_income: 0,
      marginal_band: 'higher',
      in_pa_taper: false,
    },
    tax: {
      income_tax_total: 0,
      savings_tax: 0,
      dividend_tax: 0,
      dividend_tax_before_ftcr: 0,
      ftcr: 0,
      cgt_estimate: 0,
      cgt_total: 0,
      sa_cgt_at_pre_oct_rates: 0,
      cgt_adjustment: 0,
      cgt_note: null,
      investment_only: 0,
      sa_bill: 0,
      reconciled: false,
    },
    cgt: {
      total_gain: 0,
      taxable_gain: 0,
      cgt_total: 0,
      sa_cgt_at_pre_oct_rates: 0,
      cgt_adjustment: 0,
      split_applies: false,
      dates_known: false,
      needs_box_51_adjustment: false,
      adjustment_note: null,
      buckets: [],
    },
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
    self_assessment: emptySelfAssessment(),
    marginal: { income_rate: 0.4, effective_rate: 0.4 },
  },
  tips: [
    tip({
      id: 'pension_headroom',
      title: '2025/26: £22,928.01 of 2022/23 allowance expired unused',
      status: 'lost',
      status_note: '£22,928.01 of unused 2022/23 allowance expired on 5 Apr 2026',
    }),
    tip({
      id: 'cgt_harvest',
      title: '£3,000 of CGT allowance unused',
      status: 'expiring',
      status_note: '£3,000 of the annual exempt amount expires on 5 Apr 2026',
      estimated_win_gbp: 720,
    }),
    tip({
      id: 'eri',
      title: 'Just so you know',
      how_to_execute: ['Ask payroll for a one-off AVC', 'Pay it before 5 Apr'],
    }),
  ],
  filing_deadline: '2027-01-31',
  year: {
    personal_allowance: 12570,
    pa_taper_start: 100000,
    pa_taper_end: 125140,
    basic_band: 37700,
    higher_rate_limit: 125140,
    cgt_allowance: 3000,
    dividend_allowance: 500,
    income_rates: { basic: 0.2, higher: 0.4, additional: 0.45 },
    dividend_rates: { basic: 0.0875, higher: 0.3375, additional: 0.3935 },
    cgt_rates_shares: { basic: 0.18, higher: 0.24 },
  },
  year_parameters: [
    {
      title: 'Income tax bands (taxable income, after allowances)',
      source: 'https://www.gov.uk/government/publications/rates-and-allowances-income-tax',
      rows: [
        { label: 'Additional rate above', value: 125140, kind: 'money' },
        { label: 'Rates (basic / higher / additional)', value: '20% / 40% / 45%', kind: 'text' },
      ],
    },
  ],
}

afterEach(() => vi.unstubAllGlobals())

function mockFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () => (url.endsWith('/inputs') ? {} : planner),
    })),
  )
}

test('a benefit that is gone reads red, one about to go reads orange', async () => {
  mockFetch()
  render(<PlannerView year={2025} />)

  const lost = (await screen.findByText(/expired unused/)).closest('.tip-card')!
  expect(lost.className).toContain('tip-lost')
  expect(lost.querySelector('.badge.bad')!.textContent).toBe('benefit lost')
  expect(lost.querySelector('.tip-status.lost')!.textContent).toContain('expired on 5 Apr 2026')

  const expiring = screen.getByText('£3,000 of CGT allowance unused').closest('.tip-card')!
  expect(expiring.className).toContain('tip-expiring')
  expect(expiring.querySelector('.badge.warn')!.textContent).toBe('expiring')
  // The win badge stays alongside it — the tip is still worth acting on.
  expect(expiring.querySelector('.badge.ok')!.textContent).toContain('save ~£720')

  const plain = screen.getByText('Just so you know').closest('.tip-card')!
  expect(plain.className).not.toMatch(/tip-(lost|expiring)/)
  expect(plain.querySelector('.tip-status')).toBeNull()
})

test('the how-to steps stay folded away until the card is opened', async () => {
  mockFetch()
  render(<PlannerView year={2025} />)

  const card = (await screen.findByText('Just so you know')).closest('.tip-card')!
  expect(card.querySelector('.tip-steps')).toBeNull()

  fireEvent.click(card)
  const steps = card.querySelectorAll('.tip-steps li')
  expect([...steps].map((li) => li.textContent)).toEqual([
    'Ask payroll for a one-off AVC',
    'Pay it before 5 Apr',
  ])
})

test('the year parameters are on the page, with the gov.uk page they came from', async () => {
  mockFetch()
  render(<PlannerView year={2025} />)

  // Folded away by default: the figures are for checking, not for reading every
  // time. Opening the section shows them with their source.
  const section = (await screen.findByText(/2025\/26 tax year parameters/)).closest('section')!
  fireEvent.click(screen.getByText(/2025\/26 tax year parameters/))
  expect(section.textContent).toContain('Additional rate above')
  expect(section.textContent).toContain('£125,140')
  expect(section.textContent).toContain('20% / 40% / 45%')
  expect(section.querySelector('a[href*="gov.uk"]')).not.toBeNull()
})
