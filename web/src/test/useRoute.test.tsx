import { act, render } from '@testing-library/react'
import { beforeEach, expect, test } from 'vitest'
import type { Page, Route } from '../hooks/useRoute'
import { readRoute, useRoute } from '../hooks/useRoute'
import { currentTaxYear } from '../utils/format'

const THIS_YEAR = currentTaxYear()

function Fixture({ page, year }: { page: Page | null; year: number }) {
  useRoute(page, year, (r: Route) => popped.push(r))
  return null
}

let popped: Route[] = []

beforeEach(() => {
  popped = []
  window.history.replaceState(null, '', '/')
})

test('reads the step and year a link names', () => {
  expect(readRoute('?year=2023&step=plan')).toEqual({ page: 'plan', year: 2023 })
})

test('ignores params it cannot use, so a stale link still opens', () => {
  expect(readRoute('?year=2023&step=nonsense')).toEqual({ page: null, year: 2023 })
  expect(readRoute('?year=1999&step=plan')).toEqual({ page: 'plan', year: null })
  expect(readRoute(`?year=${THIS_YEAR + 1}`)).toEqual({ page: null, year: null })
  expect(readRoute('')).toEqual({ page: null, year: null })
})

test('the landing step replaces the blank URL, later moves push', () => {
  const before = window.history.length
  const { rerender } = render(<Fixture page="report" year={2023} />)
  expect(window.location.search).toBe('?year=2023&step=report')
  expect(window.history.length).toBe(before)

  rerender(<Fixture page="plan" year={2023} />)
  expect(window.location.search).toBe('?year=2023&step=plan')
  expect(window.history.length).toBe(before + 1)
})

test('the year picker moves the URL too', () => {
  const { rerender } = render(<Fixture page="report" year={2023} />)
  rerender(<Fixture page="report" year={2022} />)
  expect(window.location.search).toBe('?year=2022&step=report')
})

test('leaves the URL alone until there is somewhere to say', () => {
  render(<Fixture page={null} year={2023} />)
  expect(window.location.search).toBe('')
})

test('Back reports where it landed, and writing that back adds no entry', () => {
  const { rerender } = render(<Fixture page="report" year={2023} />)
  rerender(<Fixture page="plan" year={2023} />)
  const after = window.history.length

  act(() => {
    window.history.replaceState(null, '', '/?year=2023&step=report')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  expect(popped).toEqual([{ page: 'report', year: 2023 }])

  // What the app does with that: set the state, which writes the URL back —
  // and finds it already there, so Back doesn't grow the history it walked.
  rerender(<Fixture page="report" year={2023} />)
  expect(window.history.length).toBe(after)
})
