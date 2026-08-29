import { render } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { useTipTaps } from '../hooks/useTipTaps'

/** jsdom has no matchMedia; `hover` decides whether the hook takes over. */
function pointer(hover: 'hover' | 'none') {
  vi.stubGlobal(
    'matchMedia',
    (q: string) => ({ matches: hover === 'hover' && q.includes('hover: hover') }) as MediaQueryList,
  )
}

function Fixture() {
  useTipTaps()
  return (
    <div>
      <span className="tip-wrap" data-tip="one" data-testid="a">
        <b data-testid="a-inner">A</b>
      </span>
      <span className="tip-wrap" data-tip="two" data-testid="b">
        B
      </span>
      <p data-testid="elsewhere">elsewhere</p>
    </div>
  )
}

const tap = (el: Element) => el.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
const open = () =>
  [...document.querySelectorAll('[data-tip-open]')].map((e) => e.getAttribute('data-tip'))

beforeEach(() => pointer('none'))

test('a tap opens the tip it landed on, even on a child of it', () => {
  const { getByTestId } = render(<Fixture />)
  tap(getByTestId('a-inner'))
  expect(open()).toEqual(['one'])
})

test('tapping the same tip again closes it', () => {
  const { getByTestId } = render(<Fixture />)
  tap(getByTestId('a'))
  tap(getByTestId('a'))
  expect(open()).toEqual([])
})

test('only one tip is open at a time', () => {
  const { getByTestId } = render(<Fixture />)
  tap(getByTestId('a'))
  tap(getByTestId('b'))
  expect(open()).toEqual(['two'])
})

test('a tap anywhere else closes the open tip', () => {
  const { getByTestId } = render(<Fixture />)
  tap(getByTestId('a'))
  tap(getByTestId('elsewhere'))
  expect(open()).toEqual([])
})

test('a pointer that can hover is left to hover — nothing is pinned', () => {
  pointer('hover')
  const { getByTestId } = render(<Fixture />)
  tap(getByTestId('a'))
  expect(open()).toEqual([])
})
