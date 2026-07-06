import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { Category, CategoryType, Transaction, TransactionPayload } from '../api/types'
import PeriodPicker, { currentPeriod, type Period } from '../components/PeriodPicker'
import { formatCentsPlain, formatDate, formatMonthYear, parseEuroToCents } from '../lib/format'
import { useAppState } from '../state/AppState'

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
  const [period, setPeriod] = useState<Period>(() => currentPeriod())
  const [typeFilter, setTypeFilter] = useState<CategoryType | ''>('')
  const [categoryFilter, setCategoryFilter] = useState<number | ''>('')
  const [categories, setCategories] = useState<Category[]>([])
  const [transactions, setTransactions] = useState<Transaction[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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

      <TransactionForm contextId={contextId} categories={categories} onSaved={load} />

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
            <div className="ml-auto flex items-center gap-2">
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
          ) : (
            <TransactionTable transactions={transactions} />
          )}
        </section>
      )}
    </div>
  )
}

function TransactionForm({
  contextId,
  categories,
  onSaved,
}: {
  contextId: number
  categories: Category[]
  onSaved: () => void
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
      await api<Transaction>('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      // datum blijft staan voor snelle reeksinvoer
      setAmountText('')
      setDescription('')
      setEffectiveDate('')
      onSaved()
    } catch {
      setSaveError('Opslaan mislukt — probeer opnieuw')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-2xl border border-edge bg-surface p-5">
      <h2 className="text-sm font-medium">Transactie toevoegen</h2>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
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
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value === '' ? '' : Number(e.target.value))}
            className={inputClass}
          >
            <option value="">— geen —</option>
            {typeCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
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
        <div className="flex items-center gap-3 sm:col-span-2 lg:col-span-6">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
          >
            Toevoegen
          </button>
          {saveError && <p className="text-sm text-crit">{saveError}</p>}
        </div>
      </form>
    </section>
  )
}

function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  return (
    <table className="w-full min-w-[640px] text-sm">
      <thead>
        <tr className="border-b border-line text-xs text-ink-3">
          <th className="px-5 py-3 text-left font-medium">Datum</th>
          <th className="px-3 py-3 text-left font-medium">Type</th>
          <th className="px-3 py-3 text-left font-medium">Categorie</th>
          <th className="px-3 py-3 text-left font-medium">Omschrijving</th>
          <th className="px-5 py-3 text-right font-medium">Bedrag</th>
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
            <td className="whitespace-nowrap px-5 py-2 text-right">
              {formatCentsPlain(tx.amount_cents)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
