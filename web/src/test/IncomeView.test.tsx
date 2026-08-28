import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import IncomeView from '../views/IncomeView'

afterEach(() => vi.unstubAllGlobals())
beforeEach(() => localStorage.clear())

function mockFetch(saved: Record<string, unknown> = {}) {
  const puts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(init.body as string))
        return { ok: true, status: 200, json: async () => ({}) }
      }
      return { ok: true, status: 200, json: async () => saved }
    }),
  )
  return puts
}

const view = (onChange = () => {}) => (
  <IncomeView year={2024} status={null} onChange={onChange} onGoTo={() => {}} />
)

test('the P60 leads the page — everything else is priced off it', async () => {
  // The old Planner opened with three pension boxes and buried the P60 below
  // them, though for an additional-rate salary the PAYE shortfall is routinely
  // the larger half of the bill.
  mockFetch()
  render(view())

  const groups = [...(await screen.findAllByRole('heading', { level: 3 }))].map(
    (h) => h.textContent,
  )
  expect(groups[0]).toContain('Employment & PAYE')
  expect(groups[1]).toContain('Pension contributions')
})

test('what HMRC actually charged is no longer an input here', async () => {
  // It feeds no calculation and belongs in the History row it explains.
  mockFetch()
  render(view())
  await screen.findByText(/Employment & PAYE/)
  expect(screen.queryByText(/What HMRC actually charged/)).toBeNull()
})

test('an unsaved edit says so, because nothing is recomputed until it is saved', async () => {
  const puts = mockFetch()
  const onChange = vi.fn()
  render(view(onChange))

  await screen.findByText(/Employment & PAYE/)
  expect(screen.getByText('All changes saved')).toBeInTheDocument()

  fireEvent.change(screen.getByPlaceholderText('e.g. 1257L'), { target: { value: '1257L' } })
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(puts).toHaveLength(1))
  expect(puts[0]).toEqual({ employments: [{ tax_code: '1257L' }] })
  // The rail and every downstream page recompute off the saved figures.
  expect(onChange).toHaveBeenCalled()
  await screen.findByText(/Saved\./)
})

test('save is inert until something actually changed', async () => {
  mockFetch({ pension_employee: 1000 })
  render(view())
  await screen.findByText(/Employment & PAYE/)
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
})

test('a P60 row left blank is dropped rather than saved as a job that paid nothing', async () => {
  const puts = mockFetch()
  render(view())

  await screen.findByText(/Employment & PAYE/)
  fireEvent.change(screen.getByPlaceholderText('e.g. 1257L'), { target: { value: 'X' } })
  fireEvent.click(screen.getByText('+ Add another employment'))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))

  await waitFor(() => expect(puts).toHaveLength(1))
  expect(puts[0]).toEqual({ employments: [{ tax_code: 'X' }] })
})
