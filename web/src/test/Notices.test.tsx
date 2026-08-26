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

test('resolved notice renders green with the arithmetic check', () => {
  const notices: Notice[] = [
    {
      ...base,
      key: 'amount_adjusted__META__2025-02-25',
      kind: 'warning',
      category: 'amount_adjusted',
      title: 'META sale — proceeds adjusted',
      resolution: {
        note: 'RSU sell-to-cover',
        data: { withholding: '10966.96' },
        evidence_name: 'trade.pdf',
        created_at: '2026-08-26 10:00:00',
        verified: true,
        check: '$45,694.37 − $10,966.96 withholding = $34,727.41 ✓ matches',
      },
    },
  ]
  const { container } = render(<Notices notices={notices} onChange={() => {}} />)
  expect(container.querySelector('.notice-resolved')).not.toBeNull()
  expect(screen.getByText('1 confirmed')).toBeInTheDocument()
  expect(screen.getByText(/matches/)).toHaveClass('ok')
  expect(screen.getByRole('link', { name: /trade\.pdf/ })).toHaveAttribute(
    'href',
    '/api/notices/amount_adjusted__META__2025-02-25/evidence',
  )
})

test('Notices renders nothing when empty', () => {
  const { container } = render(<Notices notices={[]} />)
  expect(container.innerHTML).toBe('')
})
