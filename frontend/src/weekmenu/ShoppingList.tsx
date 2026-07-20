// Boodschappenlijst (Fase 5): automatisch afgeleid uit de recepten van de huidige
// week + handmatig toegevoegde items. Geen weeknavigatie — dit scherm toont altijd
// de huidige week; GET synct de automatische items server-side (zie crud.py
// sync_and_get_shopping_list) en bewaart welke items al afgevinkt zijn.
//
// Pantry-ingrediënten komen pas in deze lijst als ze in de "Nodig uit
// voorraadkast"-dropdown als 'niet op voorraad' aangevinkt zijn (GET
// /pantry-check) — zo blijft de hoofdlijst opgeruimd i.p.v. vol te staan met
// dingen die je toch al in huis hebt.

import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { IconTrash } from '../components/icons'
import {
  addShoppingListItem,
  deleteShoppingListItem,
  getPantryCheck,
  getShoppingList,
  patchIngredient,
  patchShoppingListItem,
} from './api'
import type { PantryCheckItem, ShoppingListItemRow } from './types'
import { ErrorCard, inputClass, primaryButtonClass } from './ui'
import { useAttributes } from './useAttributes'

function mondayOf(d: Date): Date {
  const day = d.getDay() // 0 = zondag
  const diff = day === 0 ? -6 : 1 - day
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + diff)
}

function toIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const MONDAY_ISO = toIso(mondayOf(new Date()))

export default function ShoppingList() {
  const { attributes } = useAttributes()
  const [items, setItems] = useState<ShoppingListItemRow[] | null>(null)
  const [pantryCheck, setPantryCheck] = useState<PantryCheckItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [pantryBusyId, setPantryBusyId] = useState<number | null>(null)

  const [name, setName] = useState('')
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [quantity, setQuantity] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    Promise.all([getShoppingList(MONDAY_ISO), getPantryCheck(MONDAY_ISO)])
      .then(([shoppingList, pantry]) => {
        setItems(shoppingList)
        setPantryCheck(pantry)
      })
      .catch(() => setError('Boodschappenlijst laden mislukt — probeer opnieuw'))
  }, [])

  useEffect(load, [load])

  const shoppingCategories = useMemo(() => attributes?.shoppingCategories ?? [], [attributes])

  useEffect(() => {
    if (categoryId === '' && shoppingCategories.length > 0) {
      setCategoryId(shoppingCategories[0].id)
    }
  }, [categoryId, shoppingCategories])

  const grouped = useMemo(() => {
    if (items === null) return []
    return shoppingCategories
      .map((category) => ({
        category,
        rows: items.filter((item) => item.category_id === category.id),
      }))
      .filter((group) => group.rows.length > 0)
  }, [items, shoppingCategories])

  async function toggleChecked(item: ShoppingListItemRow) {
    setBusyId(item.id)
    const previous = items
    const nextChecked = !item.checked
    setItems((rows) => rows!.map((r) => (r.id === item.id ? { ...r, checked: nextChecked } : r)))
    try {
      const saved = await patchShoppingListItem(item.id, nextChecked)
      setItems((rows) => rows!.map((r) => (r.id === item.id ? saved : r)))
      // Net gekocht → automatisch weer "op voorraad" op de achtergrond. Het item
      // verdwijnt pas bij de VOLGENDE keer dat de lijst geladen wordt (niet nu
      // meteen), anders zou het tijdens het winkelen onder je vingers verdwijnen.
      if (nextChecked && item.in_stock === false && item.ingredient_id) {
        await patchIngredient(item.ingredient_id, { in_stock: true })
      }
    } catch {
      setItems(previous)
      setError('Bijwerken mislukt — probeer opnieuw')
    } finally {
      setBusyId(null)
    }
  }

  async function remove(item: ShoppingListItemRow) {
    setBusyId(item.id)
    try {
      await deleteShoppingListItem(item.id)
      setItems((rows) => rows!.filter((r) => r.id !== item.id))
    } catch {
      setError('Verwijderen mislukt — probeer opnieuw')
    } finally {
      setBusyId(null)
    }
  }

  async function toggleNeeded(item: PantryCheckItem) {
    setPantryBusyId(item.ingredient_id)
    try {
      await patchIngredient(item.ingredient_id, { in_stock: !item.in_stock })
      load() // ververst zowel de checklist als de hoofdlijst in één keer
    } catch {
      setError('Bijwerken mislukt — probeer opnieuw')
    } finally {
      setPantryBusyId(null)
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (name.trim() === '' || categoryId === '') {
      setSaveError('Naam en categorie zijn verplicht')
      return
    }
    setSaveError(null)
    setSaving(true)
    try {
      const created = await addShoppingListItem({
        name: name.trim(),
        category_id: categoryId,
        quantity: quantity.trim() || null,
      })
      setItems((rows) => [...(rows ?? []), created])
      setName('')
      setQuantity('')
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Toevoegen mislukt — probeer opnieuw')
    } finally {
      setSaving(false)
    }
  }

  const neededCount = pantryCheck?.filter((item) => !item.in_stock).length ?? 0

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Boodschappen</h1>

      {pantryCheck !== null && pantryCheck.length > 0 && (
        <details className="rounded-2xl border border-edge bg-surface p-5 open:pb-3">
          <summary className="cursor-pointer text-sm font-medium">
            Nodig uit voorraadkast{neededCount > 0 ? ` (${neededCount})` : ''}
          </summary>
          <p className="mt-2 text-xs text-ink-3">
            Vink aan wat niet meer op voorraad is — dat komt dan in de boodschappenlijst
            hieronder.
          </p>
          <ul className="mt-3 divide-y divide-line">
            {pantryCheck.map((item) => (
              <li key={item.ingredient_id} className="flex items-center gap-3 py-2 text-sm">
                <input
                  type="checkbox"
                  checked={!item.in_stock}
                  disabled={pantryBusyId === item.ingredient_id}
                  onChange={() => void toggleNeeded(item)}
                  aria-label={`${item.name} nodig uit voorraadkast`}
                  className="size-4 shrink-0 rounded border-edge accent-accent"
                />
                <span className="min-w-0 flex-1 truncate">
                  {item.name}
                  {item.quantity && (
                    <span className="ml-1.5 text-xs text-ink-3">({item.quantity})</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <section className="rounded-2xl border border-edge bg-surface p-5">
        <h2 className="text-sm font-medium">Item toevoegen</h2>
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
          <label className="block min-w-40">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
              Categorie
            </span>
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(Number(e.target.value))}
              className={inputClass}
            >
              {shoppingCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block w-32">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
              Hoeveelheid
            </span>
            <input
              type="text"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="bv. 2 stuks"
              className={inputClass}
            />
          </label>
          <button type="submit" disabled={saving} className={primaryButtonClass}>
            Toevoegen
          </button>
        </form>
        {saveError && <p className="mt-2 text-sm text-crit">{saveError}</p>}
      </section>

      {error && <ErrorCard message={error} onRetry={load} />}

      {!error &&
        (items === null ? (
          <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
        ) : grouped.length === 0 ? (
          <p className="rounded-2xl border border-edge bg-surface px-5 py-10 text-center text-sm text-ink-2">
            Nog niets op de lijst — plan recepten in de week of voeg hierboven een item toe.
          </p>
        ) : (
          <div className="space-y-4">
            {grouped.map(({ category, rows }) => (
              <section key={category.id} className="rounded-2xl border border-edge bg-surface">
                <div className="flex items-center gap-2 border-b border-line px-5 py-2.5">
                  <span
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: category.color }}
                    aria-hidden
                  />
                  <h3 className="text-sm font-medium">{category.name}</h3>
                </div>
                <ul className="divide-y divide-line">
                  {rows.map((item) => (
                    <li key={item.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                      <input
                        type="checkbox"
                        checked={item.checked}
                        disabled={busyId === item.id}
                        onChange={() => void toggleChecked(item)}
                        className="size-4 shrink-0 rounded border-edge accent-accent"
                      />
                      <span
                        className={`min-w-0 flex-1 truncate ${item.checked ? 'text-ink-3 line-through' : ''}`}
                      >
                        {item.name}
                        {item.quantity && (
                          <span className="ml-1.5 text-xs text-ink-3">({item.quantity})</span>
                        )}
                      </span>
                      {!item.manually_added && (
                        <span className="shrink-0 rounded-full bg-raised px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-3">
                          Menu
                        </span>
                      )}
                      {item.manually_added && (
                        <button
                          onClick={() => void remove(item)}
                          disabled={busyId === item.id}
                          aria-label={`${item.name} verwijderen`}
                          className="shrink-0 rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-page hover:text-ink-2 disabled:opacity-50"
                        >
                          <IconTrash className="size-4" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        ))}
    </div>
  )
}
