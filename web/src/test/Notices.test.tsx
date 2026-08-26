import { render, screen } from '@testing-library/react'
import Notices, { Hl } from '../components/Notices'
import type { Notice } from '../types'

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
      kind: 'warning',
      category: 'withholding',
      title: '[[META]] dividends taxed above the treaty rate',
      summary: 'x',
      occurrences: ['a', 'b'],
      why: 'because',
      action: 'do this',
      count: 2,
      raw: ['raw1', 'raw2'],
    },
    {
      kind: 'info',
      category: 'bed_and_breakfast',
      title: '30-day rule applied to [[META]]',
      summary: 'y',
      occurrences: [],
      why: null,
      action: null,
      count: 1,
      raw: [],
    },
  ]
  const { container } = render(<Notices notices={notices} />)
  expect(screen.getByText('1 warning · 1 note')).toBeInTheDocument()
  expect(container.querySelector('.notice-warning')).not.toBeNull()
  expect(container.querySelector('.notice-info')).not.toBeNull()
  expect(screen.getByText('×2')).toBeInTheDocument()
})

test('Notices renders nothing when empty', () => {
  const { container } = render(<Notices notices={[]} />)
  expect(container.innerHTML).toBe('')
})
