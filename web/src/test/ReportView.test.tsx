import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { ConfirmProvider } from '../components/ConfirmDialog'
import type { CalcError } from '../types'
import ReportView from '../views/ReportView'

const balanceError: CalcError = {
  type: 'negative_balance',
  message:
    "Freetrade's running GBP cash balance goes negative (-2532.71), so money left the " +
    'account that your documents never show arriving.',
  broker: 'Freetrade',
  currency: 'GBP',
  balance: '-2532.71',
  ledger: [
    { note: '1 earlier transaction(s) omitted' },
    {
      date: '2023-09-14',
      action: 'TRANSFER',
      symbol: null,
      description: 'Top up',
      amount: '1000.00',
      balance: '1000.00',
    },
    {
      date: '2024-06-14',
      action: 'BUY',
      symbol: 'GB00BP243M73',
      description: 'UK T-Bill 15/07/24',
      amount: '-3035.83',
      balance: '-2532.71',
    },
  ],
}

function mockFetch() {
  const posts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/calc/run') {
        posts.push(JSON.parse(init!.body as string))
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: 1, tax_year: 2024, status: 'error', error: balanceError }),
        }
      }
      return { ok: false, status: 404, json: async () => ({ error: 'Not found' }) }
    }),
  )
  return posts
}

afterEach(() => vi.unstubAllGlobals())

async function calculateAndFail() {
  const posts = mockFetch()
  render(
    <ConfirmProvider>
      <ReportView year={2024} status={null} onChange={() => {}} onGoTo={() => {}} />
    </ConfirmProvider>,
  )
  fireEvent.click(await screen.findByRole('button', { name: 'Calculate' }))
  await screen.findByText('Cash balance check failed')
  return posts
}

test('the balance failure is a summary, with the ledger folded away', async () => {
  await calculateAndFail()
  // The engine's transaction dump never reaches the page as one wall of text.
  expect(document.body.textContent).not.toContain('FreetradeTransaction(')
  expect(document.body.textContent).not.toContain('--no-balance-check')
  expect(screen.getByText(/goes negative/)).toBeInTheDocument()

  const details = document.querySelector('details.error-details')!
  expect(details.hasAttribute('open')).toBe(false)
  expect(details.textContent).toContain('UK T-Bill 15/07/24')
  expect(details.textContent).toContain('1 earlier transaction(s) omitted')
})

test('waiving the balance check needs a confirmation first', async () => {
  const posts = await calculateAndFail()
  expect(posts).toEqual([{ year: 2024, force: true, balance_check: true }])

  fireEvent.click(screen.getByRole('button', { name: /without the balance check/ }))
  await screen.findByText('Recalculate without the cash-balance check?')
  // Backing out must not run anything.
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(posts).toHaveLength(1))

  fireEvent.click(screen.getByRole('button', { name: /without the balance check/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Run without the check' }))
  await waitFor(() => expect(posts).toHaveLength(2))
  expect(posts[1]).toEqual({ year: 2024, force: true, balance_check: false })
})
