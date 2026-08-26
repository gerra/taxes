import { useEffect, useState } from 'react'
import { api } from './api'
import { useAuth } from './hooks/useAuth'
import { lastElapsedTaxYear, taxYearLabel } from './utils/format'
import AdminView from './views/AdminView'
import DocumentsView from './views/DocumentsView'
import LoginView from './views/LoginView'
import PlannerView from './views/PlannerView'
import ReportView from './views/ReportView'

const TABS = ['Documents', 'Report', 'Planner'] as const
type Tab = (typeof TABS)[number] | 'Admin'

const CURRENT = lastElapsedTaxYear()

export default function App() {
  const { user, loading, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('Documents')
  const [year, setYear] = useState(CURRENT)
  // Only years the backend has constants for (core/tax_years.py), newest first,
  // and never a year that hasn't finished yet.
  const [years, setYears] = useState<number[]>([CURRENT])
  // Admin only: pending access requests, shown as a badge on the Admin tab.
  const [pending, setPending] = useState(0)

  useEffect(() => {
    setPending(user?.pending_requests ?? 0)
  }, [user])

  useEffect(() => {
    if (!user) return
    api
      .get<{ years: number[] }>('/api/report/years')
      .then((r) => {
        const usable = r.years.filter((y) => y <= CURRENT).sort((a, b) => b - a)
        if (usable.length) setYears(usable)
      })
      .catch(() => {})
  }, [user])

  if (loading) return <div className="center-page">Loading…</div>
  if (!user) return <LoginView />

  return (
    <div className="app">
      <header className="topbar">
        <h1>
          <img src="/favicon.svg" alt="" className="logo-mark small" />
          <span className="wordmark">taxes</span>
        </h1>
        <nav>
          {TABS.map((t) => (
            <button key={t} className={t === tab ? 'tab active' : 'tab'} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
          {user.is_admin && (
            <button
              className={tab === 'Admin' ? 'tab active' : 'tab'}
              onClick={() => setTab('Admin')}
              title="Manage who can sign in"
            >
              Admin
              {pending > 0 && <span className="tab-count">{pending}</span>}
            </button>
          )}
        </nav>
        <div className="topbar-right">
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            title="Tax year (6 Apr – 5 Apr)"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {taxYearLabel(y)}
              </option>
            ))}
          </select>
          <button className="link" onClick={logout} title={user.email}>
            Sign out
          </button>
        </div>
      </header>
      <main>
        {tab === 'Documents' && <DocumentsView year={year} />}
        {tab === 'Report' && <ReportView year={year} />}
        {tab === 'Planner' && <PlannerView year={year} />}
        {tab === 'Admin' && user.is_admin && <AdminView onPendingCount={setPending} />}
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
