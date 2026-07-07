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

// Rekeningstatus (spec §6). Bedragen signed integer-centen.
export type AccountType = 'zicht' | 'spaar' | 'belegging' | 'andere'

export interface Account {
  id: number
  name: string
  type: AccountType
}

export interface AccountBalance {
  account_id: number
  balance_cents: number
}

export interface AccountStatusRow {
  snapshot_date: string // ISO, 1e van de maand
  balances: AccountBalance[]
  total_cents: number
  change_cents: number | null
  change_pct: number | null
}

export interface AccountStatus {
  context_id: number
  accounts: Account[]
  rows: AccountStatusRow[]
  missing_current_month: boolean
  missing_account_ids: number[]
}

export interface AccountSnapshotPayload {
  account_id: number
  snapshot_date: string
  balance_cents: number
}

// Vermogensbalans (spec §9).
export type AssetClass =
  | 'contant'
  | 'etf_fondsen'
  | 'pensioensparen'
  | 'groepsverzekering'
  | 'woning'
  | 'aandelen'

export interface AssetValue {
  asset_class: AssetClass
  value_cents: number
}

export interface NetWorthRow {
  snapshot_date: string
  assets: AssetValue[]
  total_cents: number
  change_cents: number | null
  change_pct: number | null
}

export interface NetWorth {
  context_id: number
  rows: NetWorthRow[]
  latest_date: string | null
  latest_total_cents: number
  latest_change_cents: number | null
  latest_breakdown: AssetValue[]
}

export interface NetWorthPayload {
  context_id: number
  snapshot_date: string
  asset_class: AssetClass
  value_cents: number
}

// Beleggingen (spec §7). Hoeveelheden/koersen als exacte Decimal-strings; geld als centen.
export type SecuritySide = 'buy' | 'sell'

export interface Security {
  id: number
  name: string
  ticker: string | null
  isin: string | null
  owner_context_id: number
  suggested_ticker?: string | null // afgeleid uit de naam wanneer ticker leeg is
}

export interface SecuritySearchHit {
  symbol: string
  name: string | null
  exchange: string | null
  quote_type: string | null
}

export interface SecuritySplit {
  id: number
  security_id: number
  date: string
  ratio: string
}

export interface SecuritySplitPayload {
  security_id: number
  date: string
  ratio: string
  apply_to_other_contexts?: boolean
}

export interface SecurityPayload {
  name: string
  ticker: string | null
  isin: string | null
  owner_context_id: number
}

export interface SecurityTransaction {
  id: number
  security_id: number
  date: string
  side: SecuritySide
  shares: string
  price_per_share: string
  fee: string
  tax: string
  total: string
}

export interface SecurityTransactionPayload {
  security_id: number
  date: string
  side: SecuritySide
  shares: string
  price_per_share: string
  fee: string
  tax: string
}

export interface Position {
  security_id: number
  name: string
  ticker: string | null
  shares: string
  avg_buy_price: string | null
  cost_cents: number
  current_price: string | null
  value_cents: number | null
  gain_cents: number | null
  gain_pct: number | null
  portfolio_pct: number
}

export interface RealizedGain {
  security_id: number
  name: string
  date: string
  shares: string
  proceeds_cents: number
  cost_basis_cents: number
  gain_cents: number
  year: number
}

export interface RealizedYear {
  year: number
  gain_cents: number
}

export interface Portfolio {
  context_id: number
  positions: Position[]
  total_value_cents: number
  total_cost_cents: number
  total_gain_cents: number
  total_gain_pct: number | null
  realized_gains: RealizedGain[]
  realized_by_year: RealizedYear[]
}

export interface SecurityPricePayload {
  security_id: number
  date: string
  price: string
}

export interface PriceFetchResult {
  fetched: number
  failed: string[]
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
