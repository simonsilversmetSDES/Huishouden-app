// Omgekeerde van RecipePickerModal: gegeven een vast recept, kies een vrije dag in de
// weekplanning om het aan toe te voegen (vanuit de receptenoverview). Zelfde modal-stijl.

import { useCallback, useEffect, useState } from 'react'
import { formatDate } from '../lib/format'
import { getWeek, putWeekDay } from './api'
import type { WeekPlanDay } from './types'
import { ErrorCard, secondaryButtonClass } from './ui'
import { addDays, fromIso, mondayOf, toIso } from './weekDates'

const weekdayFmt = new Intl.DateTimeFormat('nl-BE', { weekday: 'long' })

export default function WeekSlotPickerModal({
  recipeId,
  recipeServings,
  onClose,
  onAdded,
}: {
  recipeId: number
  recipeServings: number | null
  onClose: () => void
  onAdded: () => void
}) {
  const [monday, setMonday] = useState(() => mondayOf(new Date()))
  const [days, setDays] = useState<WeekPlanDay[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)

  const mondayIso = toIso(monday)

  const load = useCallback(() => {
    setError(null)
    getWeek(mondayIso)
      .then(setDays)
      .catch(() => setError('Week laden mislukt — probeer opnieuw'))
  }, [mondayIso])

  useEffect(() => {
    setDays(null)
    load()
  }, [load])

  function choose(day: WeekPlanDay) {
    setError(null)
    setSaving(day.date)
    putWeekDay(day.date, {
      recipe_id: recipeId,
      free_text: null,
      checked: false,
      servings: recipeServings,
    })
      .then(() => onAdded())
      .catch(() => {
        setSaving(null)
        setError('Toevoegen mislukt — probeer opnieuw')
      })
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-12 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-edge bg-surface p-5 shadow-lg max-md:max-h-[85dvh] max-md:overflow-y-auto max-md:rounded-b-none max-md:pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium">Kies een vrije dag</h3>
          <button onClick={onClose} className="text-sm text-ink-3 hover:text-ink-2">
            Sluiten
          </button>
        </div>

        <div className="mt-3 flex items-center gap-1.5">
          <button
            onClick={() => setMonday((m) => addDays(m, -7))}
            className={secondaryButtonClass}
            aria-label="Vorige week"
          >
            ‹
          </button>
          <button
            onClick={() => setMonday(mondayOf(new Date()))}
            className={secondaryButtonClass}
          >
            Deze week
          </button>
          <button
            onClick={() => setMonday((m) => addDays(m, 7))}
            className={secondaryButtonClass}
            aria-label="Volgende week"
          >
            ›
          </button>
        </div>

        {error && <ErrorCard message={error} />}

        <div className="mt-3 space-y-1">
          {days === null ? (
            <p className="py-8 text-center text-sm text-ink-3">Laden…</p>
          ) : (
            days.map((day) => {
              const free = day.recipe_id === null && !day.free_text?.trim()
              return (
                <button
                  key={day.date}
                  disabled={!free || saving !== null}
                  onClick={() => choose(day)}
                  className={`flex w-full items-center justify-between rounded-lg p-2 text-left text-sm transition-colors ${
                    free ? 'hover:bg-raised' : 'opacity-40'
                  }`}
                >
                  <span className="capitalize">
                    {weekdayFmt.format(fromIso(day.date))}{' '}
                    <span className="text-ink-3">{formatDate(day.date)}</span>
                  </span>
                  {!free && <span className="text-xs text-ink-3">Al ingevuld</span>}
                  {saving === day.date && <span className="text-xs text-ink-3">Bezig…</span>}
                </button>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
