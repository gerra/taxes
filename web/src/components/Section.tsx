import { useId, useState, type ReactNode } from 'react'

const STORE_PREFIX = 'taxes.section.'

/** Remember a section's fold state across reloads — collapsing a table you
 *  never read should stay collapsed next time the report loads. */
function useFolded(id: string, defaultOpen: boolean) {
  const [open, setOpen] = useState(() => {
    try {
      const v = localStorage.getItem(STORE_PREFIX + id)
      return v === null ? defaultOpen : v === '1'
    } catch {
      return defaultOpen
    }
  })
  return [
    open,
    () =>
      setOpen((prev) => {
        try {
          localStorage.setItem(STORE_PREFIX + id, prev ? '0' : '1')
        } catch {
          /* private mode — the fold just won't stick */
        }
        return !prev
      }),
  ] as const
}

/** A report section whose body folds away.
 *
 *  The whole header row is the hit target (the chevron is only the affordance),
 *  so `actions` sits above the overlay and its clicks never toggle the fold. */
export default function Section({
  id,
  title,
  meta,
  actions,
  defaultOpen = true,
  children,
}: {
  /** Stable key for the remembered fold state. */
  id: string
  title: ReactNode
  /** Muted line beside the title — counts, totals — visible while collapsed. */
  meta?: ReactNode
  /** Controls that must not toggle the section (buttons, segmented pickers). */
  actions?: ReactNode
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, toggle] = useFolded(id, defaultOpen)
  const bodyId = useId()
  return (
    <section className={open ? 'section' : 'section folded'}>
      <div className="section-head">
        <h3 className="section-title">
          <button type="button" aria-expanded={open} aria-controls={bodyId} onClick={toggle}>
            <svg className="chev" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path
                d="M4.5 6.5 8 10l3.5-3.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {title}
          </button>
        </h3>
        {meta != null && <span className="muted small section-meta">{meta}</span>}
        {actions != null && <div className="section-actions">{actions}</div>}
      </div>
      <div className="section-body" id={bodyId} hidden={!open}>
        {children}
      </div>
    </section>
  )
}
