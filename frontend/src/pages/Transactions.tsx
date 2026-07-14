import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type {
  Category,
  CategoryType,
  Rule,
  RuleApplyResult,
  RulePayload,
  Transaction,
  TransactionPayload,
} from '../api/types'
import CategoryPicker from '../components/CategoryPicker'
import PeriodPicker, { currentPeriod, type Period } from '../components/PeriodPicker'
import { IconPlus, IconTrash } from '../components/icons'
import { formatCentsPlain, formatDate, formatMonthYear, parseEuroToCents } from '../lib/format'
import { useIsMobile } from '../lib/useMediaQuery'
import { useAppState } from '../state/AppState'

// Leereffect (spec §5.3): na een categoriecorrectie op een transactie met
// tegenpartij stellen we voor er een regel van te maken.
interface CorrectionSuggestion {
  counterpartyName: string
  categoryId: number
  categoryName: string
}

const TYPES: CategoryType[] = ['Inkomen', 'Uitgaven', 'Sparen']

const TYPE_DOT: Record<CategoryType, string> = {
  Inkomen: 'bg-income',
  Uitgaven: 'bg-expense',
  Sparen: 'bg-saving',
}

const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'
const selectClass =
  'rounded-lg border border-edge bg-surface px-2 py-1.5 text-sm text-ink-2 focus:border-accent focus:outline-none'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export default function Transactions() {
  const { contextId } = useAppState()
  const isMobile = useIsMobile()
  const [period, setPeriod] = useState<Period>(() => currentPeriod())
  const [typeFilter, setTypeFilter] = useState<CategoryType | ''>('')
  const [categoryFilter, setCategoryFilter] = useState<number | ''>('')
  const [categories, setCategories] = useState<Category[]>([])
  const [transactions, setTransactions] = useState<Transaction[] | null>(null)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [correction, setCorrection] = useState<CorrectionSuggestion | null>(null)

  useEffect(() => {
    if (contextId === null) return
    setCategoryFilter('')
    api<Category[]>(`/api/categories?context_id=${contextId}`)
      .then(setCategories)
      .catch(() => setCategories([]))
  }, [contextId])

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    const params = new URLSearchParams({ context_id: String(contextId), year: String(period.year) })
    if (period.mode === 'maand') params.set('month', String(period.month))
    if (typeFilter) params.set('type', typeFilter)
    if (categoryFilter !== '') params.set('category_id', String(categoryFilter))
    api<Transaction[]>(`/api/transactions?${params}`)
      .then(setTransactions)
      .catch(() => setError('Transacties laden mislukt — probeer opnieuw'))
  }, [contextId, period, typeFilter, categoryFilter])

  useEffect(load, [load])

  if (contextId === null) return null

  const filterCategories = categories.filter((c) => !typeFilter || c.type === typeFilter)

  // Bewerken en toevoegen gebeuren nu in een popup (spec-wens): klik op een
  // transactie opent de bewerk-modal; het plusje bovenaan opent de toevoeg-modal.
  function openEdit(tx: Transaction) {
    setEditing(tx)
    setFormOpen(true)
  }

  function openAdd() {
    setEditing(null)
    setFormOpen(true)
  }

  function closeForm() {
    setFormOpen(false)
    setEditing(null)
  }

  async function createRuleFromCorrection() {
    if (contextId === null || correction === null) return
    const payload: RulePayload = {
      context_id: contextId,
      match_field: 'counterparty_name',
      match_type: 'contains',
      match_value: correction.counterpartyName,
      category_id: correction.categoryId,
      priority: 100,
      created_from_correction: true,
    }
    try {
      await api<Rule>('/api/rules', { method: 'POST', body: JSON.stringify(payload) })
      const applied = await api<RuleApplyResult>(`/api/rules/apply?context_id=${contextId}`, {
        method: 'POST',
      })
      setCorrection(null)
      setError(null)
      if (applied.updated_count > 0) load() // nieuw gecategoriseerde rijen tonen
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Regel aanmaken mislukt — probeer opnieuw',
      )
    }
  }

  async function remove(tx: Transaction) {
    const omschrijving = tx.description ? ` "${tx.description}"` : ''
    if (!window.confirm(`Transactie${omschrijving} van ${formatDate(tx.date)} verwijderen?`)) {
      return
    }
    try {
      await api<void>(`/api/transactions/${tx.id}`, { method: 'DELETE' })
      if (editing?.id === tx.id) closeForm()
      load()
    } catch {
      setError('Verwijderen mislukt — probeer opnieuw')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold capitalize">
          {period.mode === 'maand' ? formatMonthYear(period.year, period.month) : period.year}
        </h1>
        <div className="ml-auto">
          <PeriodPicker period={period} onChange={setPeriod} />
        </div>
      </div>

      {formOpen && (
        <TransactionForm
          contextId={contextId}
          categories={categories}
          editing={editing}
          onClose={closeForm}
          onSaved={(suggestion, wasEditing) => {
            setCorrection(suggestion ?? null)
            load()
            // Bewerken sluit de popup; toevoegen laat ze open voor snelle reeksinvoer.
            if (wasEditing) closeForm()
          }}
        />
      )}

      {correction && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-accent/40 bg-surface p-4 text-sm">
          <span className="text-ink-2">
            Altijd <span className="font-medium text-ink">{correction.counterpartyName}</span> →{' '}
            <span className="font-medium text-ink">{correction.categoryName}</span>?
          </span>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => void createRuleFromCorrection()}
              className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent/85"
            >
              Regel maken
            </button>
            <button
              onClick={() => setCorrection(null)}
              className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
            >
              Nee, bedankt
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {!error && (
        <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
            <h2 className="text-sm font-medium">Transacties</h2>
            <button
              onClick={openAdd}
              aria-label="Transactie toevoegen"
              title="Transactie toevoegen"
              className="flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent/85"
            >
              <IconPlus className="size-4" />
              <span className="max-sm:sr-only">Toevoegen</span>
            </button>
            <div className="flex w-full flex-col gap-2 sm:ml-auto sm:w-auto sm:flex-row sm:items-center">
              <select
                value={typeFilter}
                onChange={(e) => {
                  setTypeFilter(e.target.value as CategoryType | '')
                  setCategoryFilter('')
                }}
                aria-label="Filter op type"
                className={selectClass}
              >
                <option value="">Alle types</option>
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <select
                value={categoryFilter}
                onChange={(e) =>
                  setCategoryFilter(e.target.value === '' ? '' : Number(e.target.value))
                }
                aria-label="Filter op categorie"
                className={selectClass}
              >
                <option value="">Alle categorieën</option>
                {filterCategories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {transactions === null ? (
            <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
          ) : transactions.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-ink-2">
              Nog geen transacties in deze periode.
            </p>
          ) : isMobile ? (
            <TransactionCards transactions={transactions} onEdit={openEdit} onDelete={remove} />
          ) : (
            <TransactionTable transactions={transactions} onEdit={openEdit} onDelete={remove} />
          )}
        </section>
      )}
    </div>
  )
}

// Popup voor toevoegen én bewerken: hergebruikt hetzelfde formulier. Bij bewerken
// sluit de aanroeper de modal na opslaan; bij toevoegen blijft ze open (velden
// leeg, datum blijft) voor snelle reeksinvoer.
function TransactionForm({
  contextId,
  categories,
  editing,
  onClose,
  onSaved,
}: {
  contextId: number
  categories: Category[]
  editing: Transaction | null
  onClose: () => void
  onSaved: (correction: CorrectionSuggestion | undefined, wasEditing: boolean) => void
}) {
  const [date, setDate] = useState(todayIso)
  const [type, setType] = useState<CategoryType>('Uitgaven')
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [amountText, setAmountText] = useState('')
  const [description, setDescription] = useState('')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [amountInvalid, setAmountInvalid] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Context-wissel: categorie-keuze hoort bij de oude context, dus resetten.
  useEffect(() => setCategoryId(''), [contextId])

  // Edit-modus: formulier vullen met de transactie (bedrag terug als magnitude).
  useEffect(() => {
    if (editing === null) return
    const magnitude =
      editing.type === 'Inkomen' ? editing.amount_cents : -editing.amount_cents
    setDate(editing.date)
    setType(editing.type)
    setCategoryId(editing.category_id ?? '')
    setAmountText(formatCentsPlain(magnitude))
    setDescription(editing.description ?? '')
    setEffectiveDate(editing.effective_date !== editing.date ? editing.effective_date : '')
    setAmountInvalid(false)
    setSaveError(null)
  }, [editing])

  const typeCategories = categories.filter((c) => c.type === type)

  function changeType(next: CategoryType) {
    setType(next)
    setCategoryId('') // categorie hangt af van het type
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    const cents = parseEuroToCents(amountText)
    if (cents === null || cents === 0) {
      setAmountInvalid(true)
      return
    }
    setAmountInvalid(false)
    setSaveError(null)
    setSaving(true)
    const payload: TransactionPayload = {
      context_id: contextId,
      date,
      effective_date: effectiveDate || null,
      type,
      amount_cents: cents,
      category_id: categoryId === '' ? null : categoryId,
      description: description.trim() || null,
    }
    try {
      let suggestion: CorrectionSuggestion | undefined
      if (editing) {
        await api<void>(`/api/transactions/${editing.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
        // Leereffect: categorie gewijzigd op een transactie met tegenpartij →
        // stel voor er een regel van te maken.
        const chosen = categoryId === '' ? null : categoryId
        if (
          editing.counterparty_name &&
          chosen !== null &&
          chosen !== editing.category_id
        ) {
          const category = categories.find((c) => c.id === chosen)
          if (category) {
            suggestion = {
              counterpartyName: editing.counterparty_name,
              categoryId: category.id,
              categoryName: category.name,
            }
          }
        }
      } else {
        await api<Transaction>('/api/transactions', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      }
      // datum blijft staan voor snelle reeksinvoer
      setAmountText('')
      setDescription('')
      setEffectiveDate('')
      onSaved(suggestion, editing !== null)
    } catch {
      setSaveError('Opslaan mislukt — probeer opnieuw')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-12 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-2xl border border-edge bg-surface p-5 shadow-lg max-md:max-h-[92dvh] max-md:overflow-y-auto max-md:rounded-b-none max-md:pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-medium">
            {editing ? 'Transactie bewerken' : 'Transactie toevoegen'}
          </h2>
          <button onClick={onClose} className="text-sm text-ink-3 hover:text-ink-2">
            Sluiten
          </button>
        </div>
        <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Datum</span>
          <input
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Type</span>
          <select
            value={type}
            onChange={(e) => changeType(e.target.value as CategoryType)}
            className={inputClass}
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Categorie</span>
          <CategoryPicker
            categories={typeCategories}
            value={categoryId === '' ? null : categoryId}
            onChange={(id) => setCategoryId(id ?? '')}
            allowEmpty
            emptyLabel="— geen —"
            placeholder="Kies categorie…"
            ariaLabel="Categorie"
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Bedrag</span>
          <input
            type="text"
            inputMode="decimal"
            placeholder="0,00"
            value={amountText}
            onChange={(e) => {
              setAmountText(e.target.value)
              setAmountInvalid(false)
            }}
            aria-invalid={amountInvalid}
            className={`${inputClass} text-right tabular-nums ${
              amountInvalid ? 'border-crit' : ''
            }`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
            Omschrijving
          </span>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
            Budgetmaand (optioneel)
          </span>
          <input
            type="date"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
            className={inputClass}
          />
        </label>
        <div className="flex items-center gap-3 sm:col-span-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
          >
            {editing ? 'Opslaan' : 'Toevoegen'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 hover:bg-raised"
          >
            Annuleren
          </button>
          {saveError && <p className="text-sm text-crit">{saveError}</p>}
        </div>
        </form>
      </div>
    </div>
  )
}

// Mobiele weergave: kaartje per transactie, tap = bewerken (zelfde flow als de
// Bewerken-knop in de tabel), expliciete verwijderknop i.p.v. tekstlinks.
function TransactionCards({
  transactions,
  onEdit,
  onDelete,
}: {
  transactions: Transaction[]
  onEdit: (tx: Transaction) => void
  onDelete: (tx: Transaction) => void
}) {
  return (
    <ul className="divide-y divide-line">
      {transactions.map((tx) => (
        <li key={tx.id} className="flex items-center gap-1 px-4 py-1">
          <button
            onClick={() => onEdit(tx)}
            className="min-w-0 flex-1 py-2 text-left active:bg-raised/50"
          >
            <span className="flex items-center gap-2 text-sm">
              <span
                aria-hidden
                className={`inline-block size-2 shrink-0 rounded-full ${TYPE_DOT[tx.type]}`}
              />
              <span className="min-w-0 flex-1 truncate font-medium">
                {tx.category_name ?? <span className="font-normal text-ink-3">Geen categorie</span>}
              </span>
              <span className="shrink-0 tabular-nums">{formatCentsPlain(tx.amount_cents)}</span>
            </span>
            <span className="mt-0.5 block truncate pl-4 text-xs text-ink-3">
              {formatDate(tx.date)}
              {tx.effective_date !== tx.date && ` (telt voor ${formatDate(tx.effective_date)})`}
              {tx.description && ` · ${tx.description}`}
            </span>
          </button>
          <button
            onClick={() => onDelete(tx)}
            aria-label="Verwijderen"
            className="shrink-0 rounded-lg p-2.5 text-ink-3 transition-colors hover:text-crit active:bg-raised"
          >
            <IconTrash className="size-4" />
          </button>
        </li>
      ))}
    </ul>
  )
}

function TransactionTable({
  transactions,
  onEdit,
  onDelete,
}: {
  transactions: Transaction[]
  onEdit: (tx: Transaction) => void
  onDelete: (tx: Transaction) => void
}) {
  return (
    <table className="w-full min-w-[720px] text-sm">
      <thead>
        <tr className="border-b border-line text-xs text-ink-3">
          <th className="px-5 py-3 text-left font-medium">Datum</th>
          <th className="px-3 py-3 text-left font-medium">Type</th>
          <th className="px-3 py-3 text-left font-medium">Categorie</th>
          <th className="px-3 py-3 text-left font-medium">Omschrijving</th>
          <th className="px-3 py-3 text-right font-medium">Bedrag</th>
          <th className="px-5 py-3" />
        </tr>
      </thead>
      <tbody className="tabular-nums">
        {transactions.map((tx) => (
          <tr key={tx.id} className="border-b border-line last:border-b-0 hover:bg-raised/50">
            <td className="whitespace-nowrap px-5 py-2">
              {formatDate(tx.date)}
              {tx.effective_date !== tx.date && (
                <span className="ml-1 text-xs text-ink-3">
                  (telt voor {formatDate(tx.effective_date)})
                </span>
              )}
            </td>
            <td className="whitespace-nowrap px-3 py-2">
              <span className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={`inline-block size-2 rounded-full ${TYPE_DOT[tx.type]}`}
                />
                {tx.type}
              </span>
            </td>
            <td className="px-3 py-2">
              {tx.category_name ?? <span className="text-ink-3">–</span>}
            </td>
            <td className="max-w-64 truncate px-3 py-2 text-ink-2">{tx.description ?? ''}</td>
            <td className="whitespace-nowrap px-3 py-2 text-right">
              {formatCentsPlain(tx.amount_cents)}
            </td>
            <td className="whitespace-nowrap px-5 py-2 text-right">
              <button
                onClick={() => onEdit(tx)}
                className="text-xs text-ink-3 hover:text-ink-2 hover:underline"
              >
                Bewerken
              </button>
              <button
                onClick={() => onDelete(tx)}
                className="ml-3 text-xs text-ink-3 hover:text-crit hover:underline"
              >
                Verwijderen
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
