// Ingrediëntenbeheer: naam, pantry_type en winkelcategorie per ingrediënt.
// Elke wijziging PATCHt meteen (geen apart formulier); desktop = tabel, mobiel = kaartjes.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { useIsMobile } from '../lib/useMediaQuery'
import { listIngredients, patchIngredient } from './api'
import type { ColorAttribute, IngredientPatch, IngredientRow, PantryType } from './types'
import { PANTRY_LABEL, PANTRY_TYPES, STOCKABLE_PANTRY_TYPES } from './types'
import { ErrorCard, inputClass } from './ui'
import { useAttributes } from './useAttributes'

export default function IngredientManager() {
  const isMobile = useIsMobile()
  const { attributes } = useAttributes()
  const [rows, setRows] = useState<IngredientRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [patchError, setPatchError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const load = useCallback(() => {
    setError(null)
    listIngredients()
      .then(setRows)
      .catch(() => setError('Ingrediënten laden mislukt — probeer opnieuw'))
  }, [])

  useEffect(load, [load])

  const filtered = useMemo(() => {
    if (rows === null) return null
    const needle = search.trim().toLowerCase()
    if (needle === '') return rows
    return rows.filter((row) => row.name.toLowerCase().includes(needle))
  }, [rows, search])

  async function patch(row: IngredientRow, change: IngredientPatch) {
    setPatchError(null)
    setBusyId(row.id)
    try {
      const updated = await patchIngredient(row.id, change)
      setRows((prev) => prev?.map((r) => (r.id === row.id ? updated : r)) ?? null)
    } catch (err) {
      setPatchError(
        err instanceof ApiError
          ? `${row.name}: ${err.message}`
          : 'Wijzigen mislukt — probeer opnieuw',
      )
    } finally {
      setBusyId(null)
    }
  }

  const shoppingCategories = attributes?.shoppingCategories ?? []

  return (
    <div className="space-y-4">
      <input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Zoek ingrediënt…"
        className={inputClass}
      />

      {patchError && <p className="text-sm text-crit">{patchError}</p>}
      {error && <ErrorCard message={error} onRetry={load} />}

      {!error && (
        <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
          {filtered === null ? (
            <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
          ) : filtered.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-ink-2">
              {search.trim() !== ''
                ? 'Geen ingrediënten gevonden.'
                : 'Nog geen ingrediënten — die verschijnen bij het opslaan van recepten.'}
            </p>
          ) : isMobile ? (
            <IngredientCards
              rows={filtered}
              shoppingCategories={shoppingCategories}
              busyId={busyId}
              onPatch={patch}
            />
          ) : (
            <IngredientTable
              rows={filtered}
              shoppingCategories={shoppingCategories}
              busyId={busyId}
              onPatch={patch}
            />
          )}
        </section>
      )}
      <p className="text-xs text-ink-3">
        <strong>Altijd in huis</strong> komt nooit op de boodschappenlijst;{' '}
        <strong>Voorraadkast</strong> en <strong>Kruiden</strong> zijn afvinkbaar en
        verschijnen daar elk onder een eigen rubriek zodra je ze als 'aanvullen' aanduidt.
      </p>
    </div>
  )
}

interface RowProps {
  rows: IngredientRow[]
  shoppingCategories: ColorAttribute[]
  busyId: number | null
  onPatch: (row: IngredientRow, change: IngredientPatch) => Promise<void>
}

/** Naamveld met lokale invoerstaat: PATCHt pas bij blur of Enter, en alleen bij wijziging. */
function NameInput({
  row,
  busy,
  onRename,
}: {
  row: IngredientRow
  busy: boolean
  onRename: (name: string) => void
}) {
  const [value, setValue] = useState(row.name)
  useEffect(() => setValue(row.name), [row.name])

  function commit() {
    const trimmed = value.trim()
    if (trimmed === '' || trimmed === row.name) {
      setValue(row.name)
      return
    }
    onRename(trimmed)
  }

  return (
    <input
      type="text"
      value={value}
      disabled={busy}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur()
        }
        if (e.key === 'Escape') setValue(row.name)
      }}
      aria-label={`Naam van ${row.name}`}
      className={`${inputClass} disabled:opacity-50`}
    />
  )
}

function PantrySelect({
  row,
  busy,
  onChange,
}: {
  row: IngredientRow
  busy: boolean
  onChange: (pantryType: PantryType) => void
}) {
  return (
    <select
      value={row.pantry_type}
      disabled={busy}
      onChange={(e) => onChange(e.target.value as PantryType)}
      aria-label={`Voorraadtype van ${row.name}`}
      className={`${inputClass} disabled:opacity-50`}
    >
      {PANTRY_TYPES.map((type) => (
        <option key={type} value={type}>
          {PANTRY_LABEL[type]}
        </option>
      ))}
    </select>
  )
}

/** Enkel betekenisvol bij een afvinkbaar voorraadtype ('pantry'/'herbs') — anders een streep. */
function InStockToggle({
  row,
  busy,
  onChange,
}: {
  row: IngredientRow
  busy: boolean
  onChange: (inStock: boolean) => void
}) {
  if (!STOCKABLE_PANTRY_TYPES.includes(row.pantry_type)) {
    return <span className="text-sm text-ink-3">—</span>
  }
  return (
    <label className="flex items-center gap-1.5 text-sm">
      <input
        type="checkbox"
        checked={row.in_stock}
        disabled={busy}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={`Op voorraad: ${row.name}`}
        className="size-4 rounded border-edge accent-accent disabled:opacity-50"
      />
      {row.in_stock ? 'Op voorraad' : 'Aanvullen'}
    </label>
  )
}

function CategorySelect({
  row,
  shoppingCategories,
  busy,
  onChange,
}: {
  row: IngredientRow
  shoppingCategories: ColorAttribute[]
  busy: boolean
  onChange: (id: number | null) => void
}) {
  return (
    <select
      value={row.shopping_category_id ?? ''}
      disabled={busy}
      onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      aria-label={`Winkelcategorie van ${row.name}`}
      className={`${inputClass} disabled:opacity-50`}
    >
      <option value="">—</option>
      {shoppingCategories.map((category) => (
        <option key={category.id} value={category.id}>
          {category.name}
        </option>
      ))}
    </select>
  )
}

function IngredientTable({ rows, shoppingCategories, busyId, onPatch }: RowProps) {
  return (
    <table className="w-full min-w-[640px] text-sm">
      <thead>
        <tr className="border-b border-line text-xs text-ink-3">
          <th className="px-5 py-3 text-left font-medium">Naam</th>
          <th className="px-3 py-3 text-left font-medium">Voorraadtype</th>
          <th className="px-3 py-3 text-left font-medium">Winkelcategorie</th>
          <th className="px-3 py-3 text-left font-medium">Op voorraad</th>
          <th className="px-5 py-3 text-right font-medium">Recepten</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const busy = busyId === row.id
          return (
            <tr key={row.id} className="border-b border-line last:border-b-0 hover:bg-raised/50">
              <td className="px-5 py-1.5">
                <NameInput
                  row={row}
                  busy={busy}
                  onRename={(name) => void onPatch(row, { name })}
                />
              </td>
              <td className="px-3 py-1.5">
                <PantrySelect
                  row={row}
                  busy={busy}
                  onChange={(pantry_type) => void onPatch(row, { pantry_type })}
                />
              </td>
              <td className="px-3 py-1.5">
                <CategorySelect
                  row={row}
                  shoppingCategories={shoppingCategories}
                  busy={busy}
                  onChange={(shopping_category_id) => void onPatch(row, { shopping_category_id })}
                />
              </td>
              <td className="px-3 py-1.5">
                <InStockToggle
                  row={row}
                  busy={busy}
                  onChange={(in_stock) => void onPatch(row, { in_stock })}
                />
              </td>
              <td className="px-5 py-1.5 text-right tabular-nums text-ink-3">
                {row.recipe_count}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function IngredientCards({ rows, shoppingCategories, busyId, onPatch }: RowProps) {
  return (
    <ul className="divide-y divide-line">
      {rows.map((row) => {
        const busy = busyId === row.id
        return (
          <li key={row.id} className="space-y-2 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <NameInput
                  row={row}
                  busy={busy}
                  onRename={(name) => void onPatch(row, { name })}
                />
              </div>
              <span className="shrink-0 text-xs tabular-nums text-ink-3">
                {row.recipe_count} recept{row.recipe_count === 1 ? '' : 'en'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <PantrySelect
                row={row}
                busy={busy}
                onChange={(pantry_type) => void onPatch(row, { pantry_type })}
              />
              <CategorySelect
                row={row}
                shoppingCategories={shoppingCategories}
                busy={busy}
                onChange={(shopping_category_id) => void onPatch(row, { shopping_category_id })}
              />
            </div>
            {STOCKABLE_PANTRY_TYPES.includes(row.pantry_type) && (
              <InStockToggle
                row={row}
                busy={busy}
                onChange={(in_stock) => void onPatch(row, { in_stock })}
              />
            )}
          </li>
        )
      })}
    </ul>
  )
}
