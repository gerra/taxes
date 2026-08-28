import type { ReactNode } from 'react'
import type { StepKey, YearStatus } from '../types'

const PURPOSE: Record<StepKey, string> = {
  documents:
    'Give the calculator every transaction you have ever made. Capital gains replay your whole history, not just this year.',
  income:
    'The figures no broker export can know: your P60, pension contributions, and income taxed elsewhere.',
  report:
    'What your documents add up to: the figures to copy onto the return, and the bill they produce.',
  plan: 'Moves that would change the bill, priced at your own marginal rate.',
}

/** The top of every step page: what this step is for, and — when it is the
 *  thing to do next — one line saying why, with the button that resolves it.
 *
 *  A page that opens with its own purpose costs one line and removes the whole
 *  class of question the tab strip used to leave hanging. */
export default function StepHeader({
  step,
  status,
  title,
  children,
  onGoTo,
}: {
  step: StepKey
  status: YearStatus | null
  /** Overrides the step's own name, e.g. "Report 2024/25". */
  title: string
  /** Controls that belong to the step: Calculate, Save, Add account. */
  children?: ReactNode
  onGoTo?: (key: StepKey) => void
}) {
  const current = status?.steps.find((s) => s.key === step)
  const next = status?.next
  const isNext = next?.key === step
  // A step that is finished, on a year where something earlier is not, is worth
  // pointing back at — otherwise the user reads a green page and stops.
  const pointBack = !isNext && next && current?.state === 'done' ? next : null
  return (
    <header className="step-head">
      <div className="page-head">
        <h2>{title}</h2>
        {children}
      </div>
      <p className="step-purpose">{PURPOSE[step]}</p>
      {isNext && current && (
        <div className="step-callout">
          <b>Do this next.</b> {current.detail}
        </div>
      )}
      {pointBack && (
        <div className="step-callout muted-callout">
          This step is settled.{' '}
          {onGoTo ? (
            <button className="link" onClick={() => onGoTo(pointBack.key)}>
              {pointBack.action ?? `Go to ${pointBack.title}`}
            </button>
          ) : (
            <b>{pointBack.title}</b>
          )}{' '}
          is what still needs you — {lowerFirst(pointBack.why)}
        </div>
      )}
    </header>
  )
}

function lowerFirst(text: string): string {
  return text ? text[0].toLowerCase() + text.slice(1) : text
}
