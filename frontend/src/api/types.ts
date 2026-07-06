// Types van de backend-API. Bedragen zijn altijd integer-centen.

export type CategoryType = 'Inkomen' | 'Uitgaven' | 'Sparen'

export interface Context {
  id: number
  name: string
}

export interface TypeTotal {
  type: CategoryType
  budget_cents: number
  actual_cents: number
}

export interface CategoryStatus {
  category_id: number
  name: string
  type: CategoryType
  budget_cents: number
  actual_cents: number
}

export interface MonthTotals {
  month: number
  totals: TypeTotal[]
}

export interface DashboardData {
  context_id: number
  year: number
  month: number | null // null = heel jaar
  to_be_allocated_cents: number
  type_totals: TypeTotal[]
  categories: CategoryStatus[]
  uncategorized_count: number
  months: MonthTotals[] // altijd 12, voor de staafgrafiek
}

export interface BudgetCategoryRow {
  category_id: number
  name: string
  month_cents: number[]
  total_cents: number
}

export interface BudgetTypeGroup {
  type: CategoryType
  categories: BudgetCategoryRow[]
  monthly_total_cents: number[]
  total_cents: number
}

export interface BudgetMatrix {
  context_id: number
  year: number
  groups: BudgetTypeGroup[]
  to_be_allocated_cents: number[]
  to_be_allocated_total_cents: number
}

export interface BudgetCellUpdate {
  category_id: number
  year: number
  month: number
  amount_cents: number
}
