import { useEffect } from 'react'
import type { StepKey } from '../types'
import { currentTaxYear } from '../utils/format'

/** Where the app is, as two query params: `?year=2024&step=report`.
 *
 *  The URL is a mirror of state, not a source of navigation: nothing here ever
 *  reloads the page or refetches on its own. Opening a link reads the params
 *  once for the initial state; every move after that writes them back with the
 *  History API, so switching a step stays as instant as it was before the URL
 *  learned to follow along.
 *
 *  Query params rather than paths (`/2024/report`) because the params can't
 *  collide with the API routes, and the server needs no new rules to serve a
 *  deep link — `/?year=…` is the same index.html it already serves. */

export type Page = StepKey | 'history' | 'admin'

const PAGES: Page[] = ['documents', 'income', 'report', 'plan', 'history', 'admin']

export interface Route {
  /** null when the URL doesn't say — the caller then picks its own landing. */
  page: Page | null
  year: number | null
}

/** The params as they are right now. Anything unrecognised reads as absent, so
 *  a hand-edited or stale URL lands on the defaults instead of a blank page. */
export function readRoute(search = window.location.search): Route {
  const params = new URLSearchParams(search)
  const step = params.get('step')
  const page = PAGES.find((p) => p === step) ?? null
  const raw = params.get('year')
  const year = raw !== null && /^\d{4}$/.test(raw) ? Number(raw) : null
  // A year the app can't have data for is no year at all. The real check is
  // against the backend's list, which arrives later; this only rejects nonsense.
  const usable = year !== null && year >= 2000 && year <= currentTaxYear() ? year : null
  return { page, year: usable }
}

/** Keeps the URL showing `page` and `year`, and calls `onPop` when Back or
 *  Forward moves it. Pass a null page while there is nothing to show yet — not
 *  signed in, or still deciding where to land — and the URL is left alone.
 *
 *  The first write replaces the entry (the step the app lands you on is not
 *  somewhere you navigated from); every later one pushes, so Back walks the
 *  steps in the order they were visited. */
export function useRoute(page: Page | null, year: number, onPop: (r: Route) => void) {
  useEffect(() => {
    const handler = () => onPop(readRoute())
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [onPop])

  useEffect(() => {
    if (page === null) return
    const next = `?year=${year}&step=${page}`
    // Also the guard that stops a popstate from bouncing back as a new entry:
    // Back sets the state, the state writes the URL, and the URL already matches.
    if (window.location.search === next) return
    const url = window.location.pathname + next + window.location.hash
    if (readRoute().page === null) window.history.replaceState(null, '', url)
    else window.history.pushState(null, '', url)
  }, [page, year])
}
