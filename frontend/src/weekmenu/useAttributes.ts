// Haalt de vier attribuutlijsten + winkelcategorieën in één keer op — vrijwel elke
// weekmenu-pagina heeft ze nodig voor pills, labels en selects.

import { useCallback, useEffect, useState } from 'react'
import { listAttributes } from './api'
import type { Attribute, ColorAttribute } from './types'

export interface Attributes {
  moments: Attribute[]
  categories: ColorAttribute[]
  times: Attribute[]
  difficulties: Attribute[]
  shoppingCategories: ColorAttribute[]
}

export function useAttributes(): {
  attributes: Attributes | null
  error: string | null
  reload: () => void
} {
  const [attributes, setAttributes] = useState<Attributes | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    setError(null)
    Promise.all([
      listAttributes<Attribute>('moments'),
      listAttributes<ColorAttribute>('categories'),
      listAttributes<Attribute>('times'),
      listAttributes<Attribute>('difficulties'),
      listAttributes<ColorAttribute>('shopping-categories'),
    ])
      .then(([moments, categories, times, difficulties, shoppingCategories]) =>
        setAttributes({ moments, categories, times, difficulties, shoppingCategories }),
      )
      .catch(() => setError('Instellingen laden mislukt — probeer opnieuw'))
  }, [])

  useEffect(reload, [reload])

  return { attributes, error, reload }
}

export function attributeName(list: Attribute[], id: number | null): string | null {
  if (id === null) return null
  return list.find((a) => a.id === id)?.name ?? null
}
