/**
 * The 2024/25 split-rate year, rendered from the real API payload.
 *
 * fixtures/report-2024.json is GET /api/report/2024 for the fixture in
 * tests/test_estimator_return_2024.py — regenerate it from there if the view
 * model changes, rather than hand-editing the numbers.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { ConfirmProvider } from '../components/ConfirmDialog'
import ReportView from '../views/ReportView'
import report from './fixtures/report-2024.json'

function mockReport() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/report/2024') {
        return { ok: true, status: 200, json: async () => report }
      }
      return { ok: false, status: 404, json: async () => ({ error: 'Not found' }) }
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

async function renderReport() {
  mockReport()
  render(
    <ConfirmProvider>
      <ReportView year={2024} />
    </ConfirmProvider>,
  )
  await waitFor(() => expect(screen.getByText(/CGT rates changed on/)).toBeInTheDocument())
}

test('the rate-change banner says a box 51 adjustment is needed and how much', async () => {
  await renderReport()
  const banner = screen.getByText(/CGT rates changed on/).closest('.banner')!
  expect(banner.textContent).toContain('30 Oct 2024')
  expect(banner.textContent).toContain('£2,524.95')
  expect(banner.textContent).toContain('£6,038.57')
  expect(banner.textContent).toContain('box 51')
  // The return's own figure, the adjustment, and what is actually due.
  expect(banner.textContent).toContain('£1,112.60')
  expect(banner.textContent).toContain('£121.32')
  expect(banner.textContent).toContain('£1,233.92')
  // Never the flat-24% answer.
  expect(document.body.textContent).not.toContain('£1,335.24')
})

test('capital gains are shown at both rates, not one', async () => {
  await renderReport()
  // The rate split lives on the by-source investment breakdown, which with no
  // P60 is the bill card's own headline breakdown.
  const row = [...document.querySelectorAll('.investment-breakdown > div')].find((d) =>
    d.textContent?.startsWith('Capital gains'),
  )!
  expect(row.textContent).toContain('@ 20%')
  expect(row.textContent).toContain('@ 24%')
})

test('payments on account show both conditions and exclude CGT', async () => {
  await renderReport()
  const note = screen.getByText(/Payments on account:/).closest('.total-note')!
  expect(note.textContent).toContain('none due')
  expect(note.textContent).toContain('Balancing payment over £1,000')
  // The balancing payment is income tax owed after everything collected at
  // source, with each income source rounded down the way HMRC rounds it.
  expect(note.textContent).toContain('£235.29')
  expect(note.textContent).toContain('Under 80% collected at source')
  expect(note.textContent).toContain('capital gains tax and student loan excluded')
  // The old, wrong test compared the £1,000 threshold with the headline bill.
  expect(document.body.textContent).not.toContain('If this exceeds £1,000')
})

test('the balancing payment is not the tax on investment income', async () => {
  await renderReport()
  const note = screen.getByText(/Payments on account:/).closest('.total-note')!
  // This fixture has no P60, so PAYE is assumed correct and the note says so
  // rather than quietly presenting an assumption as a computed figure.
  expect(note.textContent).toContain('No P60 entered')
})

test('without a P60 the headline is investment income and says what it excludes', async () => {
  await renderReport()
  expect(screen.getByText(/Estimated tax on investment income/)).toBeTruthy()
  expect(document.body.textContent).toContain(
    'Excludes any PAYE under- or over-collection on salary',
  )
  // The old headline claimed to be the Self Assessment bill outright.
  expect(document.body.textContent).not.toContain('Estimated tax to pay via Self Assessment')
})

test('the distributions table classifies REITs and bond funds out of dividends', async () => {
  await renderReport()
  const table = screen.getByRole('heading', { name: /Distributions, classified/ })
    .nextElementSibling!.nextElementSibling as HTMLTableElement
  const row = (ticker: string) => within(table).getByText(ticker).closest('tr')!.textContent ?? ''
  expect(row('LAND')).toContain('REIT PID (property income)')
  expect(row('PHP')).toContain('REIT PID (property income)')
  expect(row('VGOV')).toContain('Bond fund interest')
  expect(row('VUSC')).toContain('Bond fund interest')
  expect(row('ERNS')).toContain('Bond fund interest')
  expect(row('META')).toContain('Foreign dividend')
  // The audit columns: original currency and the HMRC rate used.
  expect(row('META')).toContain('USD')
  expect(row('META')).toContain('1.2657')
})
