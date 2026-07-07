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

export interface Category {
  id: number
  name: string
  type: CategoryType
}

export interface CategoryPayload {
  context_id: number
  name: string
  type: CategoryType
}

export interface Transaction {
  id: number
  context_id: number
  date: string // ISO
  effective_date: string // ISO; budgetmaand, kan afwijken van date
  type: CategoryType
  amount_cents: number // signed: + = inkomen, − = uitgave/sparen
  category_id: number | null
  category_name: string | null
  counterparty_name: string | null
  counterparty_iban: string | null
  description: string | null
  source: string
  is_internal_transfer: boolean
}

// POST/PUT-payload: amount_cents is een positieve magnitude; de server
// past het teken toe op basis van type (negatief mag = correctie).
export interface TransactionPayload {
  context_id: number
  date: string
  effective_date: string | null
  type: CategoryType
  amount_cents: number
  category_id: number | null
  description: string | null
}

// CSV-import (spec §5.2). Bedragen signed integer-centen, zoals de preview ze geeft.
export type Bank = 'KBC' | 'Fortis' | 'Andere'
export type Categorization = 'auto' | 'manual' | 'uncategorized'

export interface AccountRef {
  id: number
  name: string
  context_id: number
  context_name: string
}

export interface PreviewRow {
  date: string // ISO
  effective_date: string // ISO
  amount_cents: number // signed
  type: CategoryType
  counterparty_name: string | null
  counterparty_iban: string | null
  description: string | null
  import_hash: string
  duplicate: boolean
  is_internal_transfer: boolean
  suggested_category_id: number | null
  suggested_category_name: string | null
  matched_rule_id: number | null
}

export interface ImportPreview {
  bank: Bank
  filename: string
  account: AccountRef | null
  unmatched_ibans: string[]
  rows: PreviewRow[]
  new_count: number
  duplicate_count: number
  uncategorized_count: number
  skipped: string[]
}

export interface CommitRow {
  date: string
  effective_date: string | null
  amount_cents: number
  type: CategoryType
  counterparty_name: string | null
  counterparty_iban: string | null
  description: string | null
  import_hash: string
  category_id: number | null
  categorization: Categorization
  is_internal_transfer: boolean
}

export interface ImportCommit {
  filename: string
  bank: Bank
  account_id: number
  context_id: number
  rows: CommitRow[]
}

export interface ImportResult {
  import_id: number
  created_count: number
  duplicate_count: number
}

// Categorisatieregels (spec §5.3).
export type MatchField = 'counterparty_name' | 'counterparty_iban' | 'description'
export type MatchType = 'contains' | 'equals' | 'regex'

export interface Rule {
  id: number
  context_id: number
  priority: number
  match_field: MatchField
  match_type: MatchType
  match_value: string
  category_id: number
  category_name: string | null
  created_from_correction: boolean
}

export interface RulePayload {
  context_id: number
  match_field: MatchField
  match_type: MatchType
  match_value: string
  category_id: number
  priority: number
  created_from_correction?: boolean
}

export interface RuleApplyResult {
  updated_count: number
}
