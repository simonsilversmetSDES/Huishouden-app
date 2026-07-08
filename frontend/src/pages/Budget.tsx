import { useCallback, useEffect, useState, type DragEvent, type KeyboardEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { BudgetCellUpdate, BudgetMatrix, Category, CategoryPayload, CategoryType } from '../api/types'
import { formatCentsPlain, MAAND_KORT, parseEuroToCents } from '../lib/format'
import { useAppState } from '../state/AppState'

export default function Budget() {
  const { contextId } = useAppState()
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [matrix, setMatrix] = useState<BudgetMatrix | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [catError, setCatError] = useState<string | null>(null)

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    api<BudgetMatrix>(`/api/budgets?context_id=${contextId}&year=${year}`)
      .then(setMatrix)
      .catch(() => setError('Budget laden mislukt — probeer opnieuw'))
  }, [contextId, year])

  useEffect(load, [load])

  const save = useCallback(
    async (items: BudgetCellUpdate[]) => {
      await api<void>('/api/budgets', {
        method: 'PUT',
        body: JSON.stringify({ items }),
      })
      load()
    },
    [load],
  )

  const addCategory = useCallback(
    async (type: CategoryType, name: string): Promise<boolean> => {
      if (contextId === null) return false
      setCatError(null)
      const payload: CategoryPayload = { context_id: contextId, name, type }
      try {
        await api<Category>('/api/categories', { method: 'POST', body: JSON.stringify(payload) })
        load()
        return true
      } catch (err) {
        setCatError(
          err instanceof ApiError && err.status === 409
            ? `Categorie "${name}" bestaat al in deze context`
            : 'Categorie toevoegen mislukt — probeer opnieuw',
        )
        return false
      }
    },
    [contextId, load],
  )

  const deleteCategory = useCallback(
    async (id: number, name: string) => {
      if (
        !window.confirm(
          `Categorie "${name}" verwijderen? Ze verdwijnt uit de kiezers en de budgetmatrix; ` +
            'bestaande transacties houden hun categorie.',
        )
      ) {
        return
      }
      setCatError(null)
      try {
        await api<void>(`/api/categories/${id}`, { method: 'DELETE' })
        load()
      } catch {
        setCatError('Categorie verwijderen mislukt — probeer opnieuw')
      }
    },
    [load],
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold">Budget {year}</h1>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => setYear((y) => y - 1)}
            aria-label="Vorig jaar"
            className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
          >
            ‹
          </button>
          <button
            onClick={() => setYear((y) => y + 1)}
            aria-label="Volgend jaar"
            className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
          >
            ›
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {catError && (
        <div className="rounded-2xl border border-crit/40 bg-surface p-4 text-sm text-crit">
          {catError}
        </div>
      )}

      {!error && matrix && (
        <MatrixTable
          matrix={matrix}
          year={year}
          onSave={save}
          onAddCategory={addCategory}
          onDeleteCategory={deleteCategory}
        />
      )}
      {!error && !matrix && <p className="py-12 text-center text-sm text-ink-3">Laden…</p>}

      <p className="text-xs text-ink-3">
        Klik een cel om te bewerken · Enter = opslaan · Esc = annuleren · Ctrl+Enter = waarde
        doortrekken t/m december · sleep een bedrag naar een andere cel om het te verplaatsen
      </p>
    </div>
  )
}

interface MatrixTableProps {
  matrix: BudgetMatrix
  year: number
  onSave: (items: BudgetCellUpdate[]) => Promise<void>
  onAddCategory: (type: CategoryType, name: string) => Promise<boolean>
  onDeleteCategory: (id: number, name: string) => void
}

function MatrixTable({ matrix, year, onSave, onAddCategory, onDeleteCategory }: MatrixTableProps) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[980px] border-collapse text-sm">
        <thead>
          <tr className="text-xs text-ink-3">
            <th className="sticky left-0 z-10 bg-surface px-4 py-3 text-left font-medium">
              Categorie
            </th>
            {MAAND_KORT.map((m) => (
              <th key={m} className="px-2 py-3 text-right font-medium">
                {m}
              </th>
            ))}
            <th className="px-4 py-3 text-right font-medium">Totaal</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          <tr className="border-t border-line">
            <td className="sticky left-0 z-10 bg-surface px-4 py-2.5 font-medium">
              Te verdelen
            </td>
            {matrix.to_be_allocated_cents.map((cents, i) => (
              <td key={i} className={`px-2 py-2.5 text-right ${tbaClass(cents)}`}>
                {formatCentsPlain(cents)}
              </td>
            ))}
            <td
              className={`px-4 py-2.5 text-right font-medium ${tbaClass(
                matrix.to_be_allocated_total_cents,
              )}`}
            >
              {formatCentsPlain(matrix.to_be_allocated_total_cents)}
            </td>
          </tr>

          {matrix.groups.map((group) => (
            <GroupRows
              key={group.type}
              group={group}
              year={year}
              onSave={onSave}
              onAddCategory={onAddCategory}
              onDeleteCategory={onDeleteCategory}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function tbaClass(cents: number): string {
  if (cents < 0) return 'text-crit'
  if (cents > 0) return 'text-good'
  return 'text-ink-3'
}

function GroupRows({
  group,
  year,
  onSave,
  onAddCategory,
  onDeleteCategory,
}: {
  group: BudgetMatrix['groups'][number]
  year: number
  onSave: (items: BudgetCellUpdate[]) => Promise<void>
  onAddCategory: (type: CategoryType, name: string) => Promise<boolean>
  onDeleteCategory: (id: number, name: string) => void
}) {
  return (
    <>
      <tr className="border-t border-line">
        <td
          colSpan={14}
          className="sticky left-0 bg-surface px-4 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-ink-3"
        >
          {group.type}
        </td>
      </tr>
      {group.categories.map((row) => (
        <tr key={row.category_id} className="group/row">
          <td className="sticky left-0 z-10 bg-surface px-4 py-1 text-ink-2">
            <div className="flex items-center gap-2">
              <span className="max-w-48 truncate">{row.name}</span>
              <button
                onClick={() => onDeleteCategory(row.category_id, row.name)}
                aria-label={`Categorie ${row.name} verwijderen`}
                title="Categorie verwijderen"
                className="text-ink-3 opacity-0 transition-opacity hover:text-crit group-hover/row:opacity-100"
              >
                ×
              </button>
            </div>
          </td>
          {row.month_cents.map((cents, monthIdx) => (
            <EditableCell
              key={monthIdx}
              categoryId={row.category_id}
              year={year}
              month={monthIdx + 1}
              cents={cents}
              onSave={onSave}
            />
          ))}
          <td className="px-4 py-1 text-right text-ink-2">
            {row.total_cents !== 0 ? formatCentsPlain(row.total_cents) : ''}
          </td>
        </tr>
      ))}
      <AddCategoryRow type={group.type} onAdd={onAddCategory} />
      <tr className="border-t border-line/60">
        <td className="sticky left-0 z-10 bg-surface px-4 py-2 text-xs text-ink-3">
          Totaal {group.type.toLowerCase()}
        </td>
        {group.monthly_total_cents.map((cents, i) => (
          <td key={i} className="px-2 py-2 text-right text-xs text-ink-3">
            {cents !== 0 ? formatCentsPlain(cents) : ''}
          </td>
        ))}
        <td className="px-4 py-2 text-right text-xs text-ink-3">
          {formatCentsPlain(group.total_cents)}
        </td>
      </tr>
    </>
  )
}

function AddCategoryRow({
  type,
  onAdd,
}: {
  type: CategoryType
  onAdd: (type: CategoryType, name: string) => Promise<boolean>
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  function close() {
    setOpen(false)
    setName('')
  }

  async function submit() {
    const trimmed = name.trim()
    if (!trimmed) return
    setBusy(true)
    const ok = await onAdd(type, trimmed)
    setBusy(false)
    if (ok) close()
  }

  return (
    <tr>
      <td colSpan={14} className="sticky left-0 bg-surface px-4 py-1.5">
        {open ? (
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={name}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void submit()
                } else if (e.key === 'Escape') {
                  close()
                }
              }}
              placeholder={`Nieuwe ${type.toLowerCase()}-categorie`}
              className="w-56 rounded-lg border border-accent bg-page px-2 py-1 text-sm focus:outline-none"
            />
            <button
              onClick={() => void submit()}
              disabled={busy}
              className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent/85 disabled:opacity-50"
            >
              Toevoegen
            </button>
            <button onClick={close} className="text-xs text-ink-3 hover:text-ink-2">
              Annuleren
            </button>
          </div>
        ) : (
          <button onClick={() => setOpen(true)} className="text-xs text-ink-3 hover:text-accent">
            + categorie
          </button>
        )}
      </td>
    </tr>
  )
}

function EditableCell({
  categoryId,
  year,
  month,
  cents,
  onSave,
}: {
  categoryId: number
  year: number
  month: number
  cents: number
  onSave: (items: BudgetCellUpdate[]) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [invalid, setInvalid] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  // Verslepen: bedrag verhuist van bron- naar doelcel (bron wordt leeg, doel overschreven).
  async function onDrop(e: DragEvent<HTMLTableCellElement>) {
    e.preventDefault()
    setDragOver(false)
    const raw = e.dataTransfer.getData('application/x-budget-cell')
    if (!raw) return
    let src: { categoryId: number; month: number; cents: number }
    try {
      src = JSON.parse(raw)
    } catch {
      return
    }
    if (src.cents === 0) return
    if (src.categoryId === categoryId && src.month === month) return // zelfde cel
    setBusy(true)
    try {
      await onSave([
        { category_id: categoryId, year, month, amount_cents: src.cents },
        { category_id: src.categoryId, year, month: src.month, amount_cents: 0 },
      ])
    } finally {
      setBusy(false)
    }
  }

  function start() {
    setText(cents !== 0 ? formatCentsPlain(cents) : '')
    setInvalid(false)
    setEditing(true)
  }

  async function commit(fillToDecember: boolean) {
    const parsed = parseEuroToCents(text)
    if (parsed === null) {
      setInvalid(true)
      return
    }
    if (parsed === cents && !fillToDecember) {
      setEditing(false)
      return
    }
    const months = fillToDecember
      ? Array.from({ length: 13 - month }, (_, i) => month + i)
      : [month]
    setBusy(true)
    try {
      await onSave(
        months.map((m) => ({
          category_id: categoryId,
          year,
          month: m,
          amount_cents: parsed,
        })),
      )
      setEditing(false)
    } catch {
      setInvalid(true)
    } finally {
      setBusy(false)
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      void commit(e.ctrlKey)
    } else if (e.key === 'Escape') {
      setEditing(false)
    }
  }

  if (!editing) {
    return (
      <td
        className={`p-0 text-right transition-colors ${
          dragOver ? 'bg-accent/15 ring-1 ring-inset ring-accent' : ''
        }`}
        onDragOver={(e) => {
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => void onDrop(e)}
      >
        <button
          onClick={start}
          draggable={cents !== 0}
          onDragStart={(e) => {
            e.dataTransfer.effectAllowed = 'move'
            e.dataTransfer.setData(
              'application/x-budget-cell',
              JSON.stringify({ categoryId, month, cents }),
            )
          }}
          className={`block w-full rounded px-2 py-1 text-right hover:bg-raised focus:outline-none focus-visible:ring-1 focus-visible:ring-accent ${
            cents !== 0 ? 'cursor-grab active:cursor-grabbing' : ''
          } ${busy ? 'opacity-50' : ''}`}
        >
          {cents !== 0 ? formatCentsPlain(cents) : <span className="text-ink-3">·</span>}
        </button>
      </td>
    )
  }

  return (
    <td className="p-0">
      <input
        autoFocus
        value={text}
        disabled={busy}
        onChange={(e) => {
          setText(e.target.value)
          setInvalid(false)
        }}
        onKeyDown={onKeyDown}
        onBlur={() => void commit(false)}
        aria-invalid={invalid}
        className={`w-full rounded border bg-page px-2 py-1 text-right focus:outline-none ${
          invalid ? 'border-crit' : 'border-accent'
        } ${busy ? 'opacity-50' : ''}`}
      />
    </td>
  )
}
