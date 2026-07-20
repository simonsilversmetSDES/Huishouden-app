// Kleine overlay om een recept te kiezen voor een weekplan-dag; zelfde
// modal-stijl als PriceChartModal (fixed overlay + stopPropagation).

import { useEffect, useMemo, useState } from 'react'
import { IconUtensils } from '../components/icons'
import { listRecipes, photoUrl } from './api'
import type { RecipeListItem } from './types'
import { ErrorCard, inputClass } from './ui'

export default function RecipePickerModal({
  onSelect,
  onClose,
}: {
  onSelect: (recipe: RecipeListItem) => void
  onClose: () => void
}) {
  const [recipes, setRecipes] = useState<RecipeListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    listRecipes()
      .then(setRecipes)
      .catch(() => setError('Recepten laden mislukt — probeer opnieuw'))
  }, [])

  const filtered = useMemo(() => {
    if (recipes === null) return null
    const needle = search.trim().toLowerCase()
    return needle === ''
      ? recipes
      : recipes.filter((r) => r.title.toLowerCase().includes(needle))
  }, [recipes, search])

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-12 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-edge bg-surface p-5 shadow-lg max-md:max-h-[85dvh] max-md:overflow-y-auto max-md:rounded-b-none max-md:pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium">Kies een recept</h3>
          <button onClick={onClose} className="text-sm text-ink-3 hover:text-ink-2">
            Sluiten
          </button>
        </div>

        <input
          type="search"
          autoFocus
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Zoek op titel…"
          className={`${inputClass} mt-3`}
        />

        <div className="mt-3 max-h-96 space-y-1 overflow-y-auto">
          {error && <ErrorCard message={error} />}
          {!error &&
            (filtered === null ? (
              <p className="py-8 text-center text-sm text-ink-3">Laden…</p>
            ) : filtered.length === 0 ? (
              <p className="py-8 text-center text-sm text-ink-3">Geen recepten gevonden.</p>
            ) : (
              filtered.map((recipe) => (
                <button
                  key={recipe.id}
                  onClick={() => onSelect(recipe)}
                  className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-raised"
                >
                  {recipe.photo_path ? (
                    <img
                      src={photoUrl(recipe.photo_path)}
                      alt=""
                      className="size-10 shrink-0 rounded-md object-cover"
                    />
                  ) : (
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-raised text-ink-3">
                      <IconUtensils className="size-4" />
                    </div>
                  )}
                  <span className="truncate text-sm">{recipe.title}</span>
                </button>
              ))
            ))}
        </div>
      </div>
    </div>
  )
}
