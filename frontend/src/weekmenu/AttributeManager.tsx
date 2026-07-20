// Generiek beheer voor één attribuuttabel (Rules.tsx-patroon: formulier bovenaan,
// lijst eronder; bewerken vult het formulier, verwijderen via confirm).

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  createAttribute,
  deleteAttribute,
  listAttributes,
  updateAttribute,
  type AttributePath,
} from './api'
import type { ColorAttribute } from './types'
import { ErrorCard, inputClass, primaryButtonClass, secondaryButtonClass } from './ui'

// Superset-type: color is alleen aanwezig/relevant wanneer hasColor waar is.
type Row = ColorAttribute

export default function AttributeManager({
  path,
  hasColor,
}: {
  path: AttributePath
  hasColor: boolean
}) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [editing, setEditing] = useState<Row | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [color, setColor] = useState('#6b7280')
  const [sortOrder, setSortOrder] = useState('0')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const formRef = useRef<HTMLElement>(null)

  const load = useCallback(() => {
    setError(null)
    listAttributes<Row>(path)
      .then(setRows)
      .catch(() => setError('Laden mislukt — probeer opnieuw'))
  }, [path])

  useEffect(load, [load])

  function startEdit(row: Row) {
    setEditing(row)
    setName(row.name)
    setColor(row.color ?? '#6b7280')
    setSortOrder(String(row.sort_order))
    setSaveError(null)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function resetForm() {
    setEditing(null)
    setName('')
    setColor('#6b7280')
    setSortOrder('0')
    setSaveError(null)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (name.trim() === '') {
      setSaveError('Naam is verplicht')
      return
    }
    setSaveError(null)
    setSaving(true)
    const payload: Record<string, unknown> = {
      name: name.trim(),
      sort_order: Number(sortOrder) || 0,
    }
    if (hasColor) payload.color = color
    try {
      if (editing) {
        await updateAttribute(path, editing.id, payload)
      } else {
        await createAttribute(path, payload)
      }
      resetForm()
      load()
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Opslaan mislukt — probeer opnieuw')
    } finally {
      setSaving(false)
    }
  }

  async function remove(row: Row) {
    if (!window.confirm(`"${row.name}" verwijderen?`)) return
    setSaveError(null)
    try {
      await deleteAttribute(path, row.id)
      if (editing?.id === row.id) resetForm()
      load()
    } catch (err) {
      // 409 in_use komt hier binnen met een duidelijke NL-boodschap van de server.
      setSaveError(err instanceof ApiError ? err.message : 'Verwijderen mislukt — probeer opnieuw')
    }
  }

  return (
    <div className="space-y-4">
      <section ref={formRef} className="rounded-2xl border border-edge bg-surface p-5">
        <h2 className="text-sm font-medium">{editing ? 'Bewerken' : 'Toevoegen'}</h2>
        <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-3">
          <label className="block min-w-40 flex-1">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Naam</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
            />
          </label>
          {hasColor && (
            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Kleur</span>
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="h-9 w-14 cursor-pointer rounded-lg border border-edge bg-page p-1"
              />
            </label>
          )}
          <label className="block w-24">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Volgorde</span>
            <input
              type="number"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              className={`${inputClass} text-right tabular-nums`}
            />
          </label>
          <div className="flex items-center gap-2">
            <button type="submit" disabled={saving} className={primaryButtonClass}>
              {editing ? 'Opslaan' : 'Toevoegen'}
            </button>
            {editing && (
              <button type="button" onClick={resetForm} className={secondaryButtonClass}>
                Annuleren
              </button>
            )}
          </div>
        </form>
        {saveError && <p className="mt-2 text-sm text-crit">{saveError}</p>}
      </section>

      {error && <ErrorCard message={error} onRetry={load} />}

      {!error && (
        <section className="rounded-2xl border border-edge bg-surface">
          {rows === null ? (
            <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
          ) : rows.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-ink-2">Nog geen items.</p>
          ) : (
            <ul className="divide-y divide-line">
              {rows.map((row) => (
                <li key={row.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  {hasColor && (
                    <span
                      className="size-3.5 shrink-0 rounded-full border border-edge"
                      style={{ backgroundColor: row.color }}
                      aria-hidden
                    />
                  )}
                  <span className="min-w-0 flex-1 truncate font-medium">{row.name}</span>
                  <span className="shrink-0 text-xs tabular-nums text-ink-3">
                    volgorde {row.sort_order}
                  </span>
                  <button
                    onClick={() => startEdit(row)}
                    className="shrink-0 py-1 text-xs text-ink-3 hover:text-ink-2 hover:underline"
                  >
                    Bewerken
                  </button>
                  <button
                    onClick={() => void remove(row)}
                    className="shrink-0 py-1 text-xs text-ink-3 hover:text-crit hover:underline"
                  >
                    Verwijderen
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
