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
  month_notes: (string | null)[] // 12 waarden; null = geen notitie
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

export interface BudgetNotePayload {
  category_id: number
  year: number
  month: number
  note: string // leeg = notitie verwijderen
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
export type AccountType =
  | 'zicht'
  | 'spaar'
  | 'belegging'
  | 'andere'
  | 'pensioensparen'
  | 'groepsverzekering'

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

export interface AccountPayload {
  context_id: number
  name: string
  type: AccountType
}

export interface NetWorthContextTotal {
  context_id: number
  name: string
  total_cents: number
}

export interface NetWorthSummary {
  contexts: NetWorthContextTotal[]
  total_cents: number
}

// Vermogensbalans (spec §9).
export type AssetClass =
  | 'contant'
  | 'etf_fondsen'
  | 'pensioensparen'
  | 'groepsverzekering'
  | 'woning'
  | 'aandelen'
  | 'bitcoin'

// Soort belegging; de waarden vallen samen met de overeenkomstige AssetClass.
export type SecurityKind = 'etf_fondsen' | 'aandelen' | 'bitcoin'

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

// Vermogensforecast ("Status balans" uit de Excel).
export type ForecastCellKind = 'werkelijk' | 'forecast' | 'error'

export interface ForecastCell {
  value_cents: number | null
  kind: ForecastCellKind
  override: boolean
  override_formula: string | null
  error: string | null
  note: string | null // celnotitie (Excel-achtig), los van de formule
}

export interface ForecastRow {
  asset_class: AssetClass
  formula: string
  is_default: boolean
  warnings: string[]
  cells: ForecastCell[] // 12 maanden
}

export interface ForecastMatrix {
  context_id: number
  year: number
  last_actual_month: string | null
  rows: ForecastRow[]
  totals: ForecastCell[]
}

export interface ForecastFormulaPayload {
  context_id: number
  asset_class: AssetClass
  year?: number | null
  month?: number | null
  formula: string
}

export interface ForecastNotePayload {
  context_id: number
  asset_class: AssetClass
  year: number
  month: number
  note: string // leeg = notitie verwijderen
}

export interface ForecastNetWorth {
  rows: NetWorthRow[] // eerste rij = laatste werkelijke maand (verbindingspunt)
}

// Beleggingen (spec §7). Hoeveelheden/koersen als exacte Decimal-strings; geld als centen.
export type SecuritySide = 'buy' | 'sell'

export interface Security {
  id: number
  name: string
  ticker: string | null
  isin: string | null
  owner_context_id: number
  soort: SecurityKind
  is_benchmark: boolean
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
  soort: SecurityKind
  is_benchmark: boolean
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
  day_gain_cents: number | null // (laatste koers − voorlaatste koers) × aantal
  day_gain_pct: number | null
  portfolio_pct: number
}

// Koersgrafiek-popup (Yahoo-tijdsblokken); prijzen in de noteringsmunt.
export type ChartRange = '1d' | '5d' | '1mo' | '6mo' | 'ytd' | '1y' | '5y' | 'max'

export interface PricePoint {
  t: string // ISO-datetime
  price: string // exacte Decimal-string
}

export interface PriceHistory {
  security_id: number
  ticker: string
  range: ChartRange
  currency: string | null
  prev_close: string | null // slotkoers vorige beursdag (referentielijn op 1D)
  points: PricePoint[]
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

export interface YearReturn {
  year: number
  return_pct: number | null // null = onvoldoende koersdata voor dat jaar
  start_value_cents: number
  end_value_cents: number
  net_flow_cents: number
  complete: boolean
}

export interface BenchmarkYear {
  year: number
  return_pct: number | null // null = geen jaargrens-koers binnen tolerantie
  complete: boolean
}

export interface Benchmark {
  security_id: number
  name: string
  years: BenchmarkYear[]
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
  yearly_returns: YearReturn[]
  benchmark: Benchmark | null
}

export interface SecurityPricePayload {
  security_id: number
  date: string
  price: string
}

// --- Lening & woning (spec §8) ---

export interface LoanInvestment {
  id: number
  label: string
  comment: string | null // bv. "50% van de aankoopprijs van de keuken"
  added_value_cents: number
}

export interface LoanContribution {
  id: number
  context_id: number
  amount_cents: number
  context_name: string
}

export interface Loan {
  id: number
  context_id: number
  name: string
  principal_cents: number
  annual_rate: string // exacte Decimal-string, bv. "0.0251"
  term_months: number
  start_date: string // ISO
  monthly_payment_cents: number | null // null = berekend
  property_value_paid_cents: number | null
  property_base_value_cents: number | null
  property_base_year: number | null
  indexation_rate: string | null
  investments: LoanInvestment[]
  contributions: LoanContribution[]
}

export interface LoanKpis {
  monthly_payment_cents: number
  total_payment_cents: number
  total_principal_cents: number
  total_interest_cents: number
  end_date: string
  remaining_months: number
  remaining_label: string
  elapsed_pct: number
  outstanding_cents: number
  principal_paid_pct: number
  paid_payment_cents: number
  paid_principal_cents: number
  paid_interest_cents: number
  paid_payment_pct: number
  paid_principal_pct: number
  paid_interest_pct: number
}

export interface PropertyValuation {
  estimate_cents: number
  price_paid_cents: number
  surplus_cents: number
  surplus_pct: number | null
  investments_total_cents: number
  indexed_value_cents: number
}

export interface OwnerShare {
  context_id: number
  name: string
  contribution_cents: number
  equity_incl_surplus_cents: number
  equity_excl_surplus_cents: number
}

export interface Ownership {
  remaining_after_loan_cents: number
  principal_paid_cents: number
  surplus_cents: number
  owners: OwnerShare[]
  total_excl_surplus_cents: number
  our_share_pct: number | null
}

export interface LoanScheduleRow {
  n: number
  date: string
  payment_cents: number
  interest_cents: number
  principal_cents: number
  balance_cents: number
  paid: boolean
}

export interface LoanOverview {
  loan: Loan
  kpis: LoanKpis
  valuation: PropertyValuation | null
  ownership: Ownership | null
  schedule: LoanScheduleRow[]
}

export interface LoanInvestmentPayload {
  label: string
  comment: string | null
  added_value_cents: number
}

export interface LoanContributionPayload {
  context_id: number
  amount_cents: number
}

export interface LoanPayload {
  name: string
  principal_cents: number
  annual_rate: string
  term_months: number
  start_date: string
  monthly_payment_cents: number | null
  property_value_paid_cents: number | null
  property_base_value_cents: number | null
  property_base_year: number | null
  indexation_rate: string | null
  investments: LoanInvestmentPayload[]
  contributions: LoanContributionPayload[]
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
  context_ids: number[] // entiteiten waarop de regel geldt (#9)
  applicable_context_ids: number[] // entiteiten waar de categorie(naam) actief bestaat
}

export interface RulePayload {
  context_id: number
  match_field: MatchField
  match_type: MatchType
  match_value: string
  category_id: number
  priority: number
  created_from_correction?: boolean
  context_ids?: number[] // leeg/weg = enkel de eigenaar-context (#9)
}

export interface RuleApplyResult {
  updated_count: number
}
