// Long-press als touch-vervanger voor rechtsklik (celnotities). Vuurt na 500ms
// stilhouden; beweging van meer dan 10px (= scrollen) annuleert. Het native
// contextmenu-event wordt tijdens een press onderdrukt zodat Android niet
// dubbel triggert en iOS geen selectie-callout toont.

import { useEffect, useRef } from 'react'

const DELAY_MS = 500
const SLOP_PX = 10

export interface LongPressHandlers {
  onTouchStart: (e: React.TouchEvent) => void
  onTouchMove: (e: React.TouchEvent) => void
  onTouchEnd: () => void
  onTouchCancel: () => void
}

export function useLongPress(): {
  /** Handlers voor het element; `fire` krijgt de touch-positie. */
  bind: (fire: (x: number, y: number) => void) => LongPressHandlers
} {
  const timerRef = useRef<number | null>(null)
  const startRef = useRef<{ x: number; y: number } | null>(null)

  function cancel() {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    startRef.current = null
  }

  useEffect(() => cancel, [])

  function bind(fire: (x: number, y: number) => void): LongPressHandlers {
    return {
      onTouchStart: (e) => {
        cancel()
        const t = e.touches[0]
        if (!t || e.touches.length > 1) return
        startRef.current = { x: t.clientX, y: t.clientY }
        timerRef.current = window.setTimeout(() => {
          timerRef.current = null
          const s = startRef.current
          startRef.current = null
          if (s) fire(s.x, s.y)
        }, DELAY_MS)
      },
      onTouchMove: (e) => {
        const s = startRef.current
        const t = e.touches[0]
        if (!s || !t) return
        if (Math.abs(t.clientX - s.x) > SLOP_PX || Math.abs(t.clientY - s.y) > SLOP_PX) cancel()
      },
      onTouchEnd: cancel,
      onTouchCancel: cancel,
    }
  }

  return { bind }
}
