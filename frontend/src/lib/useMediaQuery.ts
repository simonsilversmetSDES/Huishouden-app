// Reactieve media queries voor de twee mobiel-assen: layout volgt de
// viewportbreedte (zelfde grens als Tailwinds `md:`), gedrag volgt het
// pointertype (touch vs. muis).

import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
  )
}

/** Smal scherm — zelfde grens als Tailwinds `md:` (768px). */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 767px)')
}

/** Touch als primaire pointer (gsm/tablet) — voor gedragskeuzes, niet layout. */
export function useCoarsePointer(): boolean {
  return useMediaQuery('(pointer: coarse)')
}
