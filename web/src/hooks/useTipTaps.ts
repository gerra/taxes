import { useEffect } from 'react'

/** Open a tooltip by tapping it.
 *
 *  The tips are drawn on `:hover`, which a touch screen does not have. Both
 *  mobile engines fake a hover on tap, but they disagree about when they take
 *  it away again, and a tip that needs two taps on one phone and none on
 *  another is not a tip. So on a device with no real pointer this takes over:
 *  a tap opens the tip it landed on and closes whatever was open, a second tap
 *  on the same one closes it, and a tap anywhere else closes it too. The
 *  stylesheet draws `[data-tip-open]` exactly as it draws `:hover`.
 *
 *  Pointers that can hover are left alone — nothing about the desktop changes. */
export function useTipTaps() {
  useEffect(() => {
    if (window.matchMedia('(hover: hover)').matches) return

    const onPointerDown = (e: PointerEvent) => {
      const tip = e.target instanceof Element ? e.target.closest('.tip-wrap') : null
      const open = document.querySelector('[data-tip-open]')
      if (open && open !== tip) open.removeAttribute('data-tip-open')
      if (!tip) return
      if (open === tip) tip.removeAttribute('data-tip-open')
      else tip.setAttribute('data-tip-open', '')
    }

    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [])
}
