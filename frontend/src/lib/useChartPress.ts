// Grafiek-tooltips voelen op touch anders dan met een muis: recharts toont de
// tooltip zodra je het vlak aanraakt en laat ze staan tot je ergens anders tikt,
// waardoor ze tijdens het scrollen "blijft plakken". Deze hook maakt de tooltip
// op mobiel een press-to-show: zichtbaar zolang je duwt, weg zodra je loslaat.
// Op een fijne pointer (pc) blijft gewoon hoveren gelden — dan geeft de hook
// niets terug (undefined = recharts beslist zelf).

import { useState } from 'react'
import { useCoarsePointer } from './useMediaQuery'

export interface ChartPress {
  /** Aan `<Tooltip active={…} />`: boolean op touch, undefined op pc. */
  tooltipActive: boolean | undefined
  /** Op het chart-rootcomponent spreiden (BarChart/AreaChart/PieChart/…). */
  pressHandlers: {
    onTouchStart?: () => void
    onTouchMove?: () => void
    onTouchEnd?: () => void
    onTouchCancel?: () => void
  }
}

export function useChartPress(): ChartPress {
  const coarse = useCoarsePointer()
  const [active, setActive] = useState(false)

  if (!coarse) return { tooltipActive: undefined, pressHandlers: {} }

  return {
    tooltipActive: active,
    pressHandlers: {
      onTouchStart: () => setActive(true),
      onTouchMove: () => setActive(true),
      onTouchEnd: () => setActive(false),
      onTouchCancel: () => setActive(false),
    },
  }
}
