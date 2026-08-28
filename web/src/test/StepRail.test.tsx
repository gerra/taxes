import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import StepRail from '../components/StepRail'
import type { Step, YearStatus } from '../types'

const step = (over: Partial<Step> & Pick<Step, 'key' | 'title'>): Step => ({
  state: 'todo',
  headline: '',
  detail: '',
  action: null,
  ...over,
})

const status = (steps: Step[]): YearStatus => ({
  tax_year: 2024,
  label: '2024/25',
  in_progress: false,
  year_end: '2025-04-05',
  filing_deadline: '2026-01-31',
  deadline: { what: 'file', date: '2026-01-31', days: 120 },
  steps,
  next: null,
  bill: null,
})

const FOUR = [
  step({ key: 'documents', title: 'Documents', state: 'done', headline: '2 accounts' }),
  step({ key: 'income', title: 'Income', state: 'attention', headline: 'No P60' }),
  step({ key: 'report', title: 'Report', state: 'todo', headline: 'Not calculated yet' }),
  step({ key: 'plan', title: 'Plan', state: 'todo', headline: 'Needs your income' }),
]

test('each step carries its own state, so the rail says where the work stands', () => {
  render(<StepRail status={status(FOUR)} active="documents" onSelect={() => {}} loading={false} />)

  const buttons = [...document.querySelectorAll('.rail-step')]
  expect(buttons.map((b) => b.className.match(/state-\w+/)![0])).toEqual([
    'state-done',
    'state-attention',
    'state-todo',
    'state-todo',
  ])
  expect(screen.getByText('No P60')).toBeInTheDocument()
})

test('a finished step is ticked; an unfinished one keeps its number', () => {
  render(<StepRail status={status(FOUR)} active="documents" onSelect={() => {}} loading={false} />)

  const marks = [...document.querySelectorAll('.rail-mark')]
  // Documents is done, so it shows a tick rather than "1".
  expect(marks[0].querySelector('svg')).not.toBeNull()
  expect(marks[0].textContent).toBe('')
  expect(marks[2].textContent).toBe('3')
})

test('the rail is the navigation — clicking a step goes there', () => {
  const onSelect = vi.fn()
  render(<StepRail status={status(FOUR)} active="documents" onSelect={onSelect} loading={false} />)

  fireEvent.click(screen.getByText('Report'))
  expect(onSelect).toHaveBeenCalledWith('report')

  // History spans every year and nothing downstream depends on it, so it sits
  // outside the numbered chain.
  fireEvent.click(screen.getByText('History'))
  expect(onSelect).toHaveBeenCalledWith('history')
  expect(document.querySelectorAll('.rail-steps li')).toHaveLength(4)
})

test('the rail keeps its shape before the first status arrives', () => {
  render(<StepRail status={null} active="documents" onSelect={() => {}} loading={true} />)
  expect(document.querySelectorAll('.rail-step')).toHaveLength(4)
  expect(document.querySelector('.rail-steps')!.className).toContain('loading')
})
