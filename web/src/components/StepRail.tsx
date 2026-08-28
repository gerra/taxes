import type { Step, StepKey, YearStatus } from '../types'

/** The four steps of the year, as the primary navigation.
 *
 *  Tabs side by side are a filing cabinet: they say what exists, never what to
 *  do or in what order. This is the same four destinations drawn as the pipeline
 *  they actually are — documents feed the calculation, the calculation and your
 *  income feed the bill, the bill feeds the advice — with each one carrying its
 *  own state. Reading it top to bottom is the instructions. */
export default function StepRail({
  status,
  active,
  onSelect,
  loading,
}: {
  status: YearStatus | null
  active: StepKey | 'history'
  onSelect: (key: StepKey | 'history') => void
  loading: boolean
}) {
  const steps = status?.steps ?? PLACEHOLDER
  return (
    <nav className="rail" aria-label="Steps">
      <ol className={loading ? 'rail-steps loading' : 'rail-steps'}>
        {steps.map((step, i) => (
          <li key={step.key}>
            <button
              className={`rail-step state-${step.state}${active === step.key ? ' active' : ''}`}
              aria-current={active === step.key ? 'step' : undefined}
              onClick={() => onSelect(step.key)}
            >
              <StepMark state={step.state} index={i + 1} />
              <span className="rail-text">
                <span className="rail-title">{step.title}</span>
                <span className="rail-headline">{step.headline}</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      <button
        className={`rail-aside${active === 'history' ? ' active' : ''}`}
        onClick={() => onSelect('history')}
        title="Every year's estimate against what HMRC actually charged"
      >
        History
      </button>
    </nav>
  )
}

/** Numbered while there is something to do, ticked once there isn't — so a
 *  finished year reads as a row of ticks rather than a row of instructions. */
function StepMark({ state, index }: { state: Step['state']; index: number }) {
  if (state === 'done') {
    return (
      <span className="rail-mark" aria-hidden="true">
        <svg viewBox="0 0 16 16" focusable="false">
          <path
            d="M3.5 8.5 6.5 11.5 12.5 5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    )
  }
  return (
    <span className="rail-mark" aria-hidden="true">
      {index}
    </span>
  )
}

// Shown for the moment before the first status arrives, so the rail keeps its
// height and the page underneath doesn't jump.
const PLACEHOLDER: Step[] = [
  { key: 'documents', title: 'Documents', state: 'todo', headline: '…', detail: '', action: null },
  { key: 'income', title: 'Income', state: 'todo', headline: '…', detail: '', action: null },
  { key: 'report', title: 'Report', state: 'todo', headline: '…', detail: '', action: null },
  { key: 'plan', title: 'Plan', state: 'todo', headline: '…', detail: '', action: null },
]
