// Receptdetail: foto, pills, ingrediëntenlijst (met VOORRAAD-label) en bereiding.

import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { deleteRecipe, getRecipe, photoUrl } from './api'
import type { Recipe } from './types'
import { ColorPill, ErrorCard, Pill, secondaryButtonClass } from './ui'
import { attributeName, useAttributes } from './useAttributes'

export default function RecipeDetail() {
  const { id } = useParams()
  const recipeId = Number(id)
  const navigate = useNavigate()
  const { attributes } = useAttributes()
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(() => {
    setError(null)
    getRecipe(recipeId)
      .then(setRecipe)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Recept laden mislukt — probeer opnieuw'),
      )
  }, [recipeId])

  useEffect(load, [load])

  async function remove() {
    if (!recipe) return
    const confirmText =
      `Recept "${recipe.title}" verwijderen?\n\n` +
      'Staat het in je weekplanning, dan verdwijnt het daar ook; ' +
      'boodschappen-items blijven staan maar verliezen hun MENU-label.'
    if (!window.confirm(confirmText)) return
    setDeleting(true)
    try {
      await deleteRecipe(recipe.id)
      navigate('/weekmenu')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Verwijderen mislukt — probeer opnieuw')
      setDeleting(false)
    }
  }

  if (error) return <ErrorCard message={error} onRetry={load} />
  if (recipe === null) return <p className="py-12 text-center text-sm text-ink-3">Laden…</p>

  const category = attributes?.categories.find((c) => c.id === recipe.category_id)
  const moment = attributes ? attributeName(attributes.moments, recipe.moment_id) : null
  const time = attributes ? attributeName(attributes.times, recipe.time_id) : null
  const difficulty = attributes ? attributeName(attributes.difficulties, recipe.difficulty_id) : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/weekmenu" className="text-sm text-ink-3 hover:text-ink-2 hover:underline">
          ← Recepten
        </Link>
        <div className="ml-auto flex items-center gap-2">
          <Link to={`/weekmenu/recepten/${recipe.id}/bewerken`} className={secondaryButtonClass}>
            Bewerken
          </Link>
          <button
            onClick={() => void remove()}
            disabled={deleting}
            className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 transition-colors hover:bg-crit/10 hover:text-crit disabled:opacity-50"
          >
            Verwijderen
          </button>
        </div>
      </div>

      {recipe.photo_path && (
        <img
          src={photoUrl(recipe.photo_path)}
          alt={recipe.title}
          className="max-h-72 w-full rounded-2xl border border-edge object-cover"
        />
      )}

      <div className="space-y-2">
        <h1 className="text-xl font-semibold">{recipe.title}</h1>
        <div className="flex flex-wrap gap-1.5">
          {category && <ColorPill color={category.color}>{category.name}</ColorPill>}
          {moment && <Pill>{moment}</Pill>}
          {time && <Pill>{time}</Pill>}
          {difficulty && <Pill>{difficulty}</Pill>}
        </div>
        {recipe.source_url && (
          <a
            href={recipe.source_url}
            target="_blank"
            rel="noreferrer"
            className="block truncate text-sm text-accent hover:underline"
          >
            {recipe.source_url}
          </a>
        )}
      </div>

      <section className="rounded-2xl border border-edge bg-surface">
        <h2 className="border-b border-line px-5 py-3 text-sm font-medium">Ingrediënten</h2>
        {recipe.ingredients.length === 0 ? (
          <p className="px-5 py-6 text-center text-sm text-ink-3">Geen ingrediënten.</p>
        ) : (
          <ul className="divide-y divide-line">
            {recipe.ingredients.map((item) => (
              <li key={item.id} className="flex items-baseline gap-2 px-5 py-2.5 text-sm">
                <span className="w-24 shrink-0 text-right tabular-nums text-ink-2">
                  {[item.quantity, item.unit].filter(Boolean).join(' ')}
                </span>
                <span className="min-w-0 flex-1">
                  {item.name}
                  {item.note && <span className="ml-1.5 text-xs text-ink-3">({item.note})</span>}
                </span>
                {item.pantry_type === 'pantry' && (
                  <span className="shrink-0 rounded-md bg-warn/15 px-1.5 py-0.5 text-[11px] font-medium text-warn">
                    VOORRAAD
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {recipe.description && (
        <section className="rounded-2xl border border-edge bg-surface">
          <h2 className="border-b border-line px-5 py-3 text-sm font-medium">Bereiding</h2>
          <p className="whitespace-pre-line px-5 py-4 text-sm leading-relaxed text-ink-2">
            {recipe.description}
          </p>
        </section>
      )}
    </div>
  )
}
