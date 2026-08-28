import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { History } from '../types'
import HistoryView from '../views/HistoryView'

const historyWith = (actual: number | null): History => ({
  explain: 'Your estimate against what HMRC actually charged.',
  unreconciled: [],
  mismatched: [],
  years: [
    {
      tax_year: 2023,
      label: '2023/24',
      due_date: '2025-01-31',
      estimate: 683.55,
      investment_only: 120.1,
      employment_shortfall: 563.45,
      reconciled: true,
      has_report: true,
      actual,
      difference: actual === null ? null : Number((actual - 683.55).toFixed(2)),
      matches: false,
    },
  ],
})

afterEach(() => vi.unstubAllGlobals())

function mockFetch(actual: number | null = null) {
  const puts: { url: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        puts.push({ url, body: JSON.parse(init.body as string) })
        return { ok: true, status: 200, json: async () => ({ actual: 621.45 }) }
      }
      return { ok: true, status: 200, json: async () => historyWith(actual) }
    }),
  )
  return puts
}

test('what HMRC charged is typed into the row whose difference it moves', async () => {
  // It used to be one of twenty boxes on the Planner form — a figure that feeds
  // no calculation, entered months after everything else, three tabs from the
  // only table that shows it.
  const puts = mockFetch()
  render(<HistoryView onChange={() => {}} />)

  const input = await screen.findByLabelText('What HMRC actually charged for 2023/24')
  fireEvent.change(input, { target: { value: '621.45' } })
  fireEvent.blur(input)

  await waitFor(() => expect(puts).toHaveLength(1))
  expect(puts[0].url).toBe('/api/history/2023/actual')
  expect(puts[0].body).toEqual({ actual_tax_paid: 621.45 })
})

test('clearing a figure removes it rather than storing a zero', async () => {
  // A zero would read as "HMRC charged nothing", which is a real answer and a
  // wrong one; the comparison has to go back to having no answer at all.
  const puts = mockFetch(621.45)
  render(<HistoryView onChange={() => {}} />)

  const input = await screen.findByLabelText('What HMRC actually charged for 2023/24')
  expect((input as HTMLInputElement).value).toBe('621.45')
  fireEvent.change(input, { target: { value: '' } })
  fireEvent.blur(input)

  await waitFor(() => expect(puts).toHaveLength(1))
  expect(puts[0].body).toEqual({ actual_tax_paid: null })
})

test('an untouched cell saves nothing on blur', async () => {
  const puts = mockFetch(621.45)
  render(<HistoryView onChange={() => {}} />)

  fireEvent.blur(await screen.findByLabelText('What HMRC actually charged for 2023/24'))
  await Promise.resolve()
  expect(puts).toHaveLength(0)
})
