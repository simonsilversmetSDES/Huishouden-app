// Getypeerde wrappers rond de gedeelde api()-client voor /api/weekmenu/*.

import { api } from '../api/client'
import type {
  Attribute,
  IngredientPatch,
  IngredientRow,
  ParsedRecipe,
  Recipe,
  RecipeListItem,
  RecipePayload,
  WeekPlanDay,
  WeekPlanDayPayload,
} from './types'

const BASE = '/api/weekmenu'

export type ParseRequest =
  | { url: string }
  | { image_base64: string; image_media_type: string }

export const parseRecipe = (body: ParseRequest) =>
  api<ParsedRecipe>(`${BASE}/recipes/parse`, { method: 'POST', body: JSON.stringify(body) })

export const listRecipes = () => api<RecipeListItem[]>(`${BASE}/recipes`)

export const getRecipe = (id: number) => api<Recipe>(`${BASE}/recipes/${id}`)

export const createRecipe = (payload: RecipePayload) =>
  api<Recipe>(`${BASE}/recipes`, { method: 'POST', body: JSON.stringify(payload) })

export const updateRecipe = (id: number, payload: RecipePayload) =>
  api<Recipe>(`${BASE}/recipes/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const deleteRecipe = (id: number) =>
  api<void>(`${BASE}/recipes/${id}`, { method: 'DELETE' })

/** Foto's worden auth-beveiligd geserveerd; de sessiecookie gaat vanzelf mee. */
export const photoUrl = (filename: string) => `${BASE}/photos/${filename}`

export type AttributePath =
  | 'moments'
  | 'categories'
  | 'times'
  | 'difficulties'
  | 'shopping-categories'

export const listAttributes = <T extends Attribute>(path: AttributePath) =>
  api<T[]>(`${BASE}/${path}`)

export const createAttribute = <T extends Attribute>(path: AttributePath, payload: object) =>
  api<T>(`${BASE}/${path}`, { method: 'POST', body: JSON.stringify(payload) })

export const updateAttribute = <T extends Attribute>(
  path: AttributePath,
  id: number,
  payload: object,
) => api<T>(`${BASE}/${path}/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const deleteAttribute = (path: AttributePath, id: number) =>
  api<void>(`${BASE}/${path}/${id}`, { method: 'DELETE' })

export const listIngredients = () => api<IngredientRow[]>(`${BASE}/ingredients`)

export const patchIngredient = (id: number, patch: IngredientPatch) =>
  api<IngredientRow>(`${BASE}/ingredients/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })

export const getWeek = (start: string) =>
  api<WeekPlanDay[]>(`${BASE}/week?start=${start}`)

export const putWeekDay = (date: string, payload: WeekPlanDayPayload) =>
  api<WeekPlanDay>(`${BASE}/week/${date}`, { method: 'PUT', body: JSON.stringify(payload) })
