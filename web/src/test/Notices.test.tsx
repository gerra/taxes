import { render, screen } from '@testing-library/react'
import Notices, { Hl } from '../components/Notices'
import type { Notice } from '../types'

const base: Omit<Notice, 'key' | 'kind' | 'category' | 'title'> = {
  summary: 'x',
  occurrences: [],
  why: null,
  action: null,
  count: 1,
  raw: [],
  resolution: null,
  verification: { intro: '', docs: [], fields: [] },
}

test('Hl renders [[tokens]] as highlight pills', () => {
  const { container } = render(<Hl text="Sold [[10 May 2023]], bought [[16 May 2023]]" />)
  const pills = container.querySelectorAll('.hl')
  expect(pills).toHaveLength(2)
  expect(pills[0]).toHaveTextContent('10 May 2023')
  expect(container.textContent).not.toContain('[[')
})

test('Notices summarises counts and colors by kind', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'withholding__META',
      kind: 'warning',
      category: 'withholding',
      title: '[[META]] dividends taxed above the treaty rate',
      occurrences: ['a', 'b'],
      why: 'because',
      action: 'do this',
      count: 2,
      raw: ['raw1', 'raw2'],
    },
    {
      ...base,
      key: 'bed_and_breakfast__META',
      kind: 'info',
      category: 'bed_and_breakfast',
      title: '30-day rule applied to [[META]]',
    },
  ]
  const { container } = render(<Notices notices={notices} />)
  expect(screen.getByText('1 warning · 1 note')).toBeInTheDocument()
  expect(container.querySelector('.notice-warning')).not.toBeNull()
  expect(container.querySelector('.notice-info')).not.toBeNull()
  expect(screen.getByText('×2')).toBeInTheDocument()
})

test('verified notice renders green with graded checks and evidence link', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__META__2025-02-25',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'META sale — tax withheld',
      resolution: {
        note: 'backup withholding',
        data: { withholding: '10966.96', principal: '45695.65', reason: 'backup' },
        evidence_name: 'trade.pdf',
        created_at: '2026-08-26 10:00:00',
        status: 'verified',
        checks: [
          { label: 'Principal matches quantity × price', status: 'ok', detail: '70 × $652.795' },
          { label: 'Withholding explains the missing amount', status: 'ok', detail: 'matches' },
          { label: 'Tax treatment', status: 'info', detail: 'reclaim via 1040-NR' },
        ],
        missing: [],
        verified: true,
        check: 'matches',
      },
    },
  ]
  const { container } = render(<Notices notices={notices} onChange={() => {}} />)
  expect(container.querySelector('.notice-resolved')).not.toBeNull()
  expect(screen.getByText('1 verified')).toBeInTheDocument()
  expect(container.querySelectorAll('.check-ok')).toHaveLength(2)
  expect(container.querySelector('.check-info')).not.toBeNull()
  expect(screen.getByRole('link', { name: /trade\.pdf/ })).toHaveAttribute(
    'href',
    '/api/notices/amount_adjusted__META__2025-02-25/evidence',
  )
})

test('mismatch renders as error with missing answers listed', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__X__2025-01-01',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'X sale',
      resolution: {
        note: '',
        data: { withholding: '100' },
        evidence_name: null,
        created_at: '2026-08-26 10:00:00',
        status: 'mismatch',
        checks: [
          { label: 'Withholding explains the missing amount', status: 'fail', detail: 'off by $9' },
        ],
        missing: ['Principal (gross value on the trade details)'],
        verified: false,
        check: 'off by $9',
      },
    },
  ]
  const { container } = render(<Notices notices={notices} onChange={() => {}} />)
  expect(container.querySelector('.notice-error')).not.toBeNull()
  expect(screen.getByText(/Still needed/)).toHaveTextContent('Principal')
})

test('Notices renders nothing when empty', () => {
  const { container } = render(<Notices notices={[]} />)
  expect(container.innerHTML).toBe('')
})
