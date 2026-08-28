/**
 * The reconciled bill card: one card, one headline, no figure stated twice.
 *
 * The fixture has no P60, so it is patched here into a reconciled year with a
 * PAYE shortfall and an instalment already paid — the shape that used to render
 * as two identically-styled cards, the second of them often the smaller half of
 * the story at the same size as the first.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { ConfirmProvider } from '../components/ConfirmDialog'
import ReportView from '../views/ReportView'
import type { SelfAssessment } from '../types'
import base from './fixtures/report-2024.json'

const SHORTFALL = 5160.6
const PAID_ON_ACCOUNT = 1200

function reconciledReport() {
  const report = structuredClone(base) as typeof base
  const sa = report.view.tax_due.self_assessment as unknown as SelfAssessment
  sa.reconciled = true
  sa.employment_shortfall = SHORTFALL
  sa.already_paid = {
    total: PAID_ON_ACCOUNT,
    payments_on_account_made: PAID_ON_ACCOUNT,
    tax_paid_on_gains: 0,
  }
  sa.sa_bill = sa.investment_only + SHORTFALL - PAID_ON_ACCOUNT
  for (const row of sa.rows) {
    if (row.key === 'employment') row.amount = SHORTFALL
    if (row.key === 'already_paid') row.amount = -PAID_ON_ACCOUNT
    if (row.key === 'total') row.amount = sa.sa_bill
  }
  return report
}

async function renderReconciled() {
  const report = reconciledReport()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url === '/api/report/2024'
        ? { ok: true, status: 200, json: async () => report }
        : { ok: false, status: 404, json: async () => ({ error: 'Not found' }) },
    ),
  )
  render(
    <ConfirmProvider>
      <ReportView year={2024} status={null} onChange={() => {}} onGoTo={() => {}} />
    </ConfirmProvider>,
  )
  await waitFor(() =>
    expect(screen.getByText(/Estimated Self Assessment bill/)).toBeInTheDocument(),
  )
  return document.querySelector('.total-card')! as HTMLElement
}

afterEach(() => vi.unstubAllGlobals())

test('the bill is one card, not two competing headlines', async () => {
  const card = await renderReconciled()
  expect(document.querySelectorAll('.total-card').length).toBe(1)
  expect(card.querySelectorAll('.stat-value').length).toBe(1)
})

test('the headline breakdown is the equation the bill is built from', async () => {
  const card = await renderReconciled()
  const cells = [...card.querySelectorAll(':scope > .total-breakdown > div')].map(
    (d) => d.textContent ?? '',
  )
  expect(cells.length).toBe(3)
  expect(cells[0]).toContain('Employment tax shortfall')
  expect(cells[0]).toContain('£5,160.60')
  expect(cells[1]).toContain('Investment income')
  expect(cells[1]).toContain('£1,469.21')
  expect(cells[2]).toContain('Paid on account')
  expect(cells[2]).toContain('£1,200.00')
  // 5,160.60 + 1,469.21 − 1,200.00, and it is the number in the headline.
  expect(card.querySelector('.stat-value')!.textContent).toBe('£5,429.81')
})

test('the investment figures appear once, inside the inset drill-down', async () => {
  const card = await renderReconciled()
  // Not beside the bill: the top-level breakdown has no per-source rows.
  const top = card.querySelector(':scope > .total-breakdown')!.textContent ?? ''
  expect(top).not.toContain('Capital gains')
  expect(top).not.toContain('Dividends')
  const inset = card.querySelector('.of-which')!
  expect(inset.querySelector('.investment-breakdown')).toBeTruthy()
  expect(inset.textContent).toContain('Capital gains')
  expect(inset.textContent).toContain('£1,233.92')
  // The inset expands the line above rather than restating its total.
  expect(inset.querySelector('.stat-value')).toBeNull()
})
