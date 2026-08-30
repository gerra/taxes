import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import StepRail from './components/StepRail'
import { useAuth } from './hooks/useAuth'
import type { Page } from './hooks/useRoute'
import type { Route } from './hooks/useRoute'
import { readRoute, useRoute } from './hooks/useRoute'
import { useTipTaps } from './hooks/useTipTaps'
import type { StepKey, YearStatus } from './types'
import { currentTaxYear, lastElapsedTaxYear, shortDate, taxYearLabel } from './utils/format'
import AdminView from './views/AdminView'
import DocumentsView from './views/DocumentsView'
import HistoryView from './views/HistoryView'
import IncomeView from './views/IncomeView'
import LoginView from './views/LoginView'
import PlanView from './views/PlanView'
import ReportView from './views/ReportView'

// The year the app opens on is the last finished one — that's the one you file.
// The running year is offered too: it's the only one you can still change.
const LATEST_FILED = lastElapsedTaxYear()
const IN_PROGRESS = currentTaxYear()

// What the way out of Admin is called, so the link back can name its destination.
const PAGE_NAMES: Record<Page, string> = {
  documents: 'Documents',
  income: 'Income',
  report: 'Report',
  plan: 'Plan',
  history: 'History',
  admin: 'Admin',
}

export default function App() {
  const { user, loading, logout } = useAuth()
  useTipTaps()
  // A link can name the step and the year (?year=2024&step=report). Read once,
  // for the state the app starts in; from there the URL follows the state.
  const opened = useRef(readRoute()).current
  const [page, setPage] = useState<Page>(opened.page ?? 'documents')
  // The landing step is chosen once, from the first status that arrives: the
  // app opens where the work actually is rather than always at step one. Only
  // once — after that the user is navigating, and moving them would be rude.
  // A link that already named a step has landed by definition. It is also what
  // holds the URL back until the landing step is known, so the address the app
  // settles on replaces the blank one instead of stacking behind it.
  const [landed, setLanded] = useState(opened.page !== null)
  // Admin isn't a step, so it hides the rail — which leaves the link that
  // opened it as the only way back out. Remember where "back" is.
  const beforeAdmin = useRef<Page>('report')
  const [year, setYear] = useState(opened.year ?? LATEST_FILED)
  // Only years the backend has constants for (core/tax_years.py), newest first;
  // the running year is included, marked so nobody files off it.
  const [years, setYears] = useState<number[]>([LATEST_FILED])
  const [status, setStatus] = useState<YearStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(true)
  // Admin only: pending access requests, shown as a badge on the Admin link.
  const [pending, setPending] = useState(0)

  useEffect(() => {
    setPending(user?.pending_requests ?? 0)
  }, [user])

  useEffect(() => {
    if (!user) return
    api
      .get<{ years: number[] }>('/api/report/years')
      .then((r) => {
        const usable = r.years.filter((y) => y <= IN_PROGRESS).sort((a, b) => b - a)
        if (!usable.length) return
        setYears(usable)
        // A year out of a link that the backend has no constants for would sit
        // in the picker showing nothing. Fall back to the one you'd file.
        setYear((y) => (usable.includes(y) ? y : LATEST_FILED))
      })
      .catch(() => {})
  }, [user])

  // Every step's state, reloaded whenever a step changes something. It is what
  // the rail draws, and what tells each page whether it is the thing to do next.
  const reloadStatus = useCallback(() => {
    if (!user) return
    setStatusLoading(true)
    api
      .get<YearStatus>(`/api/status/${year}`)
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setStatusLoading(false))
  }, [user, year])

  useEffect(reloadStatus, [reloadStatus])

  useEffect(() => {
    if (landed || !status) return
    setLanded(true)
    // Nothing outstanding: open on the Report, which is the thing you came for.
    setPage(status.next?.key ?? 'report')
  }, [landed, status])

  // Every move the user makes, from the rail or from a page's own link. It also
  // ends the landing: from the first click on, where you are is your choice.
  const navigate = useCallback((next: Page) => {
    setLanded(true)
    setPage(next)
  }, [])

  // Admin is not a step and not everyone's to open; a link to it from someone
  // it isn't for reads as the report.
  useEffect(() => {
    if (page === 'admin' && user && !user.is_admin) setPage('report')
  }, [page, user])

  // Once signed in, the URL says where you are — and Back and Forward move you
  // between the steps you've visited, without a reload.
  const onPop = useCallback((r: Route) => {
    setPage(r.page ?? 'documents')
    if (r.year !== null) setYear(r.year)
  }, [])
  useRoute(user && landed ? page : null, year, onPop)

  if (loading) return <div className="center-page">Loading…</div>
  if (!user) return <LoginView />

  const goTo = (key: StepKey) => navigate(key)

  return (
    <div className="app">
      <header className="topbar">
        <h1>
          <img src="/favicon.svg" alt="" className="logo-mark small" />
          <span className="wordmark">taxes</span>
        </h1>
        <div className="topbar-right">
          {status && <DeadlinePill status={status} />}
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            title="Tax year (6 Apr – 5 Apr)"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {taxYearLabel(y)}
                {y === IN_PROGRESS ? ' — in progress' : ''}
              </option>
            ))}
          </select>
        </div>
        {/* The account controls are their own group so a phone can put them on
            the brand's row and give the year picker a line of its own. */}
        <div className="topbar-account">
          {user.is_admin &&
            (page === 'admin' ? (
              <button
                className="link"
                onClick={() => navigate(beforeAdmin.current)}
                title={`Back to ${PAGE_NAMES[beforeAdmin.current]}`}
              >
                ← {PAGE_NAMES[beforeAdmin.current]}
              </button>
            ) : (
              <button
                className="link"
                onClick={() => {
                  beforeAdmin.current = page
                  navigate('admin')
                }}
                title="Manage who can sign in"
              >
                Admin
                {pending > 0 && <span className="tab-count">{pending}</span>}
              </button>
            ))}
          <button className="link" onClick={logout} title={user.email}>
            Sign out
          </button>
        </div>
      </header>

      {page !== 'admin' && (
        <StepRail
          status={status}
          active={page === 'history' ? 'history' : page}
          onSelect={navigate}
          loading={statusLoading}
        />
      )}

      <main>
        {page === 'documents' && (
          <DocumentsView year={year} status={status} onChange={reloadStatus} onGoTo={goTo} />
        )}
        {page === 'income' && (
          <IncomeView year={year} status={status} onChange={reloadStatus} onGoTo={goTo} />
        )}
        {page === 'report' && (
          <ReportView year={year} status={status} onChange={reloadStatus} onGoTo={goTo} />
        )}
        {page === 'plan' && <PlanView year={year} status={status} onGoTo={goTo} />}
        {/* History spans every year, so the year picker doesn't apply to it. */}
        {page === 'history' && <HistoryView onChange={reloadStatus} />}
        {page === 'admin' && user.is_admin && <AdminView onPendingCount={setPending} />}
      </main>

      <footer className="disclaimer">
        <p>
          Computed hints from your own data — not tax advice. Verify against the HMRC forms before
          filing.
        </p>
        <p className="credit">
          Calculations by{' '}
          <a
            href="https://github.com/KapJI/capital-gains-calculator"
            target="_blank"
            rel="noreferrer"
          >
            cgt-calc
          </a>{' '}
          by Ruslan Sayfutdinov (MIT), via{' '}
          <a
            href="https://github.com/gerra/capital-gains-calculator"
            target="_blank"
            rel="noreferrer"
          >
            a small fork
          </a>
          .
        </p>
      </footer>
    </div>
  )
}

/** What the clock is running towards. A finished year has a filing date; the
 *  running one has 5 April, after which nothing in it can be changed. */
function DeadlinePill({ status }: { status: YearStatus }) {
  const { what, date, days } = status.deadline
  const overdue = days < 0
  const soon = !overdue && days <= 45
  const verb = what === 'act' ? 'to act' : 'to file'
  return (
    <span
      className={`deadline-pill${overdue ? ' overdue' : soon ? ' soon' : ''}`}
      title={
        what === 'act'
          ? `${status.label} ends ${shortDate(date)}. Allowances not used by then don't carry forward.`
          : `${status.label} must be filed online and paid by ${shortDate(date)}.`
      }
    >
      {overdue ? `${Math.abs(days)} days over` : `${days} days ${verb}`}
    </span>
  )
}
