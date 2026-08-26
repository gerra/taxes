import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export interface ConfirmOptions {
  title: string
  message?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  // Optional free-text input (e.g. a note); resolved value is passed back.
  input?: { label: string; placeholder?: string }
}

type ConfirmResult = { ok: boolean; input?: string }
type ConfirmFn = (opts: ConfirmOptions) => Promise<ConfirmResult>

const ConfirmContext = createContext<ConfirmFn>(async () => ({ ok: false }))

export function useConfirm(): ConfirmFn {
  return useContext(ConfirmContext)
}

interface Pending {
  opts: ConfirmOptions
  resolve: (r: ConfirmResult) => void
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null)
  const [input, setInput] = useState('')
  const confirmRef = useRef<HTMLButtonElement>(null)

  const confirm = useCallback<ConfirmFn>((opts) => {
    setInput('')
    return new Promise((resolve) => setPending({ opts, resolve }))
  }, [])

  const close = (ok: boolean) => {
    if (!pending) return
    pending.resolve({ ok, input: ok ? input.trim() : undefined })
    setPending(null)
  }

  useEffect(() => {
    if (!pending) return
    if (!pending.opts.input) confirmRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close(false)
      if (e.key === 'Enter' && !(e.target instanceof HTMLTextAreaElement)) close(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, input])

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <div className="modal-backdrop" onMouseDown={() => close(false)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 id="modal-title">{pending.opts.title}</h3>
            {pending.opts.message && <div className="modal-message">{pending.opts.message}</div>}
            {pending.opts.input && (
              <label className="modal-input">
                {pending.opts.input.label}
                <input
                  autoFocus
                  value={input}
                  placeholder={pending.opts.input.placeholder}
                  onChange={(e) => setInput(e.target.value)}
                />
              </label>
            )}
            <div className="modal-actions">
              <button className="btn" onClick={() => close(false)}>
                {pending.opts.cancelLabel ?? 'Cancel'}
              </button>
              <button
                ref={confirmRef}
                className={`btn primary ${pending.opts.danger ? 'danger' : ''}`}
                onClick={() => close(true)}
              >
                {pending.opts.confirmLabel ?? 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}
