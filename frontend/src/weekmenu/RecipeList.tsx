// Receptenlijst: kaartgrid met foto, titel en pills; client-side zoeken + filteren
// (2 gebruikers, kleine dataset — geen serverfilters nodig).

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { IconPlus, IconUtensils } from '../components/icons'
import { listRecipes, photoUrl } from './api'
import type { RecipeListItem } from './types'
import { ColorPill, ErrorCard, inputClass, Pill } from './ui'
import { attributeName, useAttributes } from './useAttributes'

export default function RecipeList() {
  const { attributes } = useAttributes()
  const [recipes, setRecipes] = useState<RecipeListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [momentId, setMomentId] = useState<number | null>(null)

  const load = useCallback(() => {
    setError(null)
    listRecipes()
      .then(setRecipes)
      .catch(() => setError('Recepten laden mislukt — probeer opnieuw'))
  }, [])

  useEffect(load, [load])

  const filtered = useMemo(() => {
    if (recipes === null) return null
    const needle = search.trim().toLowerCase()
    return recipes.filter(
      (r) =>
        (needle === '' || r.title.toLowerCase().includes(needle)) &&
        (categoryId === null || r.category_id === categoryId) &&
        (momentId === null || r.moment_id === momentId),
    )
  }, [recipes, search, categoryId, momentId])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Recepten</h1>
        <Link
          to="/weekmenu/recepten/nieuw"
          className="ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85"
        >
          <IconPlus className="size-4" />
          Nieuw recept
        </Link>
      </div>

      <input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Zoek op titel…"
        className={inputClass}
      />

      {attributes && (
        <div className="space-y-2">
          <div className="scrollbar-none flex gap-1.5 overflow-x-auto overscroll-x-contain">
            {attributes.moments.map((m) => (
              <FilterChip
                key={m.id}
                active={momentId === m.id}
                onClick={() => setMomentId(momentId === m.id ? null : m.id)}
              >
                {m.name}
              </FilterChip>
            ))}
            <span className="mx-1 border-l border-line" aria-hidden />
            {attributes.categories.map((c) => (
              <FilterChip
                key={c.id}
                active={categoryId === c.id}
                color={c.color}
                onClick={() => setCategoryId(categoryId === c.id ? null : c.id)}
              >
                {c.name}
              </FilterChip>
            ))}
          </div>
        </div>
      )}

      {error && <ErrorCard message={error} onRetry={load} />}

      {!error &&
        (filtered === null ? (
          <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-edge bg-surface px-5 py-10 text-center text-sm text-ink-2">
            {recipes && recipes.length > 0
              ? 'Geen recepten gevonden met deze filters.'
              : 'Nog geen recepten — voeg je eerste recept toe.'}
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((recipe) => (
              <li key={recipe.id}>
                <Link
                  to={`/weekmenu/recepten/${recipe.id}`}
                  className="block overflow-hidden rounded-2xl border border-edge bg-surface transition-colors hover:bg-raised/50"
                >
                  {recipe.photo_path ? (
                    <img
                      src={photoUrl(recipe.photo_path)}
                      alt=""
                      loading="lazy"
                      className="h-36 w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-36 w-full items-center justify-center bg-raised text-ink-3">
                      <IconUtensils className="size-8" />
                    </div>
                  )}
                  <div className="space-y-1.5 p-4">
                    <h2 className="text-sm font-medium">{recipe.title}</h2>
                    {attributes && (
                      <div className="flex flex-wrap gap-1">
                        <RecipePills recipe={recipe} attributes={attributes} />
                      </div>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}

function RecipePills({
  recipe,
  attributes,
}: {
  recipe: RecipeListItem
  attributes: NonNullable<ReturnType<typeof useAttributes>['attributes']>
}) {
  const category = attributes.categories.find((c) => c.id === recipe.category_id)
  const moment = attributeName(attributes.moments, recipe.moment_id)
  const time = attributeName(attributes.times, recipe.time_id)
  return (
    <>
      {category && <ColorPill color={category.color}>{category.name}</ColorPill>}
      {moment && <Pill>{moment}</Pill>}
      {time && <Pill>{time}</Pill>}
    </>
  )
}

function FilterChip({
  active,
  color,
  onClick,
  children,
}: {
  active: boolean
  color?: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      style={active && color ? { backgroundColor: color, color: '#fff' } : undefined}
      className={`whitespace-nowrap rounded-full px-3 py-1 text-sm transition-colors pointer-coarse:py-1.5 ${
        active ? 'bg-ink text-white' : 'text-ink-3 hover:bg-surface hover:text-ink-2'
      }`}
    >
      {children}
    </button>
  )
}
