import { useCallback, useEffect, useState, type KeyboardEvent } from 'react'
import { api } from '../api/client'
import type { BudgetCellUpdate, BudgetMatrix } from '../api/types'
import { formatCentsPlain, MAAND_KORT, parseEuroToCents } from '../lib/format'
import { useAppState } from '../state/AppState'

export default function Budget() {
  const { contextId } = useAppState()
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [matrix, setMatrix] = useState<BudgetMatrix | null>(null)
  const [error, setError] = useState<string | null>(null)

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

      {!error && matrix && <MatrixTable matrix={matrix} year={year} onSave={save} />}
      {!error && !matrix && <p className="py-12 text-center text-sm text-ink-3">Laden…</p>}

      <p className="text-xs text-ink-3">
        Klik een cel om te bewerken · Enter = opslaan · Esc = annuleren · Ctrl+Enter = waarde
        doortrekken t/m december
      </p>
    </div>
  )
}

interface MatrixTableProps {
  matrix: BudgetMatrix
  year: number
  onSave: (items: BudgetCellUpdate[]) => Promise<void>
}

function MatrixTable({ matrix, year, onSave }: MatrixTableProps) {
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
            <GroupRows key={group.type} group={group} year={year} onSave={onSave} />
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
}: {
  group: BudgetMatrix['groups'][number]
  year: number
  onSave: (items: BudgetCellUpdate[]) => Promise<void>
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
          <td className="sticky left-0 z-10 max-w-56 truncate bg-surface px-4 py-1 text-ink-2">
            {row.name}
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
      <td className="p-0 text-right">
        <button
          onClick={start}
          className="block w-full rounded px-2 py-1 text-right hover:bg-raised focus:outline-none focus-visible:ring-1 focus-visible:ring-accent"
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
