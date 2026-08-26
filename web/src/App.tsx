import { useState } from 'react'
import { useAuth } from './hooks/useAuth'
import { lastElapsedTaxYear } from './utils/format'
import DocumentsView from './views/DocumentsView'
import LoginView from './views/LoginView'
import PlannerView from './views/PlannerView'
import ReportView from './views/ReportView'

const TABS = ['Documents', 'Report', 'Planner'] as const
type Tab = (typeof TABS)[number]

const CURRENT = lastElapsedTaxYear()
const YEARS = Array.from({ length: CURRENT - 2019 }, (_, i) => CURRENT - i)

export default function App() {
  const { user, loading, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('Documents')
  const [year, setYear] = useState(CURRENT)

  if (loading) return <div className="center-page">Loading…</div>
  if (!user) return <LoginView />

  return (
    <div className="app">
      <header className="topbar">
        <h1>taxes</h1>
        <nav>
          {TABS.map((t) => (
            <button key={t} className={t === tab ? 'tab active' : 'tab'} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            title="Tax year (6 Apr – 5 Apr)"
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}/{String((y + 1) % 100).padStart(2, '0')}
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
      </main>
      <footer className="disclaimer">
        Computed hints from your own data — not tax advice. Verify against the HMRC forms before
        filing.
      </footer>
    </div>
  )
}
