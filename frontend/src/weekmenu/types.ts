// Types voor de Weekmenu-API. Veldnamen zijn Engels (bewuste beslissing,
// consistent met de db-kolommen); alle UI-labels zijn Nederlands.

export type PantryType = 'always_home' | 'pantry' | 'normal'

export const PANTRY_LABEL: Record<PantryType, string> = {
  always_home: 'Altijd in huis',
  pantry: 'Voorraadkast',
  normal: 'Normaal',
}

export const PANTRY_TYPES: PantryType[] = ['normal', 'pantry', 'always_home']

export interface Attribute {
  id: number
  name: string
  sort_order: number
}

export interface ColorAttribute extends Attribute {
  color: string
}

export interface RecipeIngredient {
  id: number
  ingredient_id: number
  name: string
  pantry_type: PantryType
  quantity: string | null
  unit: string | null
  note: string | null
}

export interface Recipe {
  id: number
  title: string
  description: string | null
  photo_path: string | null
  source_url: string | null
  moment_id: number | null
  category_id: number | null
  time_id: number | null
  difficulty_id: number | null
  ingredients: RecipeIngredient[]
}

export interface RecipeListItem {
  id: number
  title: string
  photo_path: string | null
  moment_id: number | null
  category_id: number | null
  time_id: number | null
  difficulty_id: number | null
  created_at: string
}

export interface ParsedIngredient {
  name: string
  quantity: string | null
  unit: string | null
}

/** Bewerkbaar resultaat van POST /recipes/parse — wordt nooit rechtstreeks opgeslagen. */
export interface ParsedRecipe {
  title: string
  description: string
  photo_url: string | null
  source_url: string | null
  ingredients: ParsedIngredient[]
}

export interface IngredientIn {
  name: string
  quantity: string | null
  unit: string | null
  note: string | null
}

export interface RecipePayload {
  title: string
  description: string
  source_url: string | null
  photo_url: string | null
  photo_base64: string | null
  photo_media_type: string | null
  moment_id: number | null
  category_id: number | null
  time_id: number | null
  difficulty_id: number | null
  ingredients: IngredientIn[]
  /** Alleen relevant bij PUT. */
  remove_photo?: boolean
}

export interface IngredientRow {
  id: number
  name: string
  pantry_type: PantryType
  shopping_category_id: number | null
  recipe_count: number
}

export interface IngredientPatch {
  name?: string
  pantry_type?: PantryType
  shopping_category_id?: number | null
}
