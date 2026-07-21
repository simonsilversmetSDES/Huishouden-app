// Recept bewerken: bestaand recept laden, terugmappen naar het formulier, PUT.

import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getRecipe, updateRecipe } from './api'
import RecipeForm, { type FormInitial, type PhotoState } from './RecipeForm'
import type { Recipe, RecipePayload } from './types'
import { ErrorCard } from './ui'
import { useAttributes } from './useAttributes'

export default function RecipeEdit() {
  const { id } = useParams()
  const recipeId = Number(id)
  const navigate = useNavigate()
  const { attributes, error: attrError, reload } = useAttributes()
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    getRecipe(recipeId)
      .then(setRecipe)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Recept laden mislukt — probeer opnieuw'),
      )
  }, [recipeId])

  useEffect(load, [load])

  if (error || attrError) {
    return <ErrorCard message={error ?? attrError ?? ''} onRetry={error ? load : reload} />
  }
  if (recipe === null || !attributes) {
    return <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
  }

  const initial: FormInitial = {
    title: recipe.title,
    description: recipe.description ?? '',
    source_url: recipe.source_url ?? '',
    moment_id: recipe.moment_id,
    category_ids: recipe.category_ids,
    time_id: recipe.time_id,
    difficulty_id: recipe.difficulty_id,
    servings: recipe.servings,
    ingredients: recipe.ingredients.map((item) => ({
      name: item.name,
      quantity: item.quantity,
      unit: item.unit,
      note: item.note,
    })),
  }
  const initialPhoto: PhotoState = recipe.photo_path
    ? { kind: 'keep', path: recipe.photo_path }
    : { kind: 'none' }

  async function save(payload: RecipePayload) {
    await updateRecipe(recipeId, payload)
    navigate(`/weekmenu/recepten/${recipeId}`)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to={`/weekmenu/recepten/${recipeId}`}
          className="text-sm text-ink-3 hover:text-ink-2 hover:underline"
        >
          ← Terug naar recept
        </Link>
        <h1 className="text-lg font-semibold">Recept bewerken</h1>
      </div>
      <RecipeForm
        initial={initial}
        initialPhoto={initialPhoto}
        attributes={attributes}
        submitLabel="Wijzigingen opslaan"
        onSubmit={save}
      />
    </div>
  )
}
