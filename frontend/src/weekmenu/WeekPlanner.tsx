// Weekweergave (Fase 4): per dag een recept kiezen of vrije tekst typen, met
// weeknavigatie en een afvink-toggle. Elke wijziging is direct een kleine
// PUT /api/weekmenu/week/{datum} (geen aparte "opslaan"-knop nodig).

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { IconSwap, IconTrash, IconUtensils } from '../components/icons'
import { formatDate } from '../lib/format'
import { getWeek, photoUrl, putWeekDay } from './api'
import RecipePickerModal from './RecipePickerModal'
import type { RecipeListItem, WeekPlanDay, WeekPlanDayPayload } from './types'
import { ErrorCard, inputClass, secondaryButtonClass } from './ui'
import { addDays, fromIso, mondayOf, toIso } from './weekDates'

const weekdayFmt = new Intl.DateTimeFormat('nl-BE', { weekday: 'long' })
const shortWeekdayFmt = new Intl.DateTimeFormat('nl-BE', { weekday: 'short' })
const shortDateFmt = new Intl.DateTimeFormat('nl-BE', { day: '2-digit', month: '2-digit' })

export default function WeekPlanner() {
  const [monday, setMonday] = useState(() => mondayOf(new Date()))
  const [days, setDays] = useState<WeekPlanDay[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pickerDate, setPickerDate] = useState<string | null>(null)

  const mondayIso = toIso(monday)
  const sunday = addDays(monday, 6)

  const load = useCallback(() => {
    setError(null)
    getWeek(mondayIso)
      .then(setDays)
      .catch(() => setError('Weekmenu laden mislukt — probeer opnieuw'))
  }, [mondayIso])

  useEffect(() => {
    setDays(null) // toon "Laden…" i.p.v. de vorige week te laten staan tijdens het wisselen
    load()
  }, [load])

  const saveDay = useCallback(
    (date: string, patch: Partial<WeekPlanDayPayload>) => {
      const previous = days // snapshot VOOR de optimistic update — hier draaien we bij een fout naartoe terug
      const current = previous?.find((d) => d.date === date)
      if (!current) return
      const next: WeekPlanDayPayload = {
        recipe_id: current.recipe_id,
        free_text: current.free_text,
        checked: current.checked,
        servings: current.servings,
        ...patch,
      }
      setDays((ds) => ds!.map((d) => (d.date === date ? { ...d, ...next } : d)))
      putWeekDay(date, next)
        .then((saved) => setDays((ds) => ds!.map((d) => (d.date === date ? saved : d))))
        .catch(() => {
          setDays(previous)
          setError('Opslaan mislukt — probeer opnieuw')
        })
    },
    [days],
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Week</h1>
        <div className="ml-auto flex items-center gap-1.5">
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
      </div>

      <p className="text-sm text-ink-3">
        {shortWeekdayFmt.format(monday)} {formatDate(mondayIso)} –{' '}
        {shortWeekdayFmt.format(sunday)} {formatDate(toIso(sunday))}
      </p>

      {error && <ErrorCard message={error} onRetry={load} />}

      {!error &&
        (days === null ? (
          <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
        ) : (
          <div className="space-y-2.5">
            {days.map((day) => (
              <DayRow
                key={day.date}
                day={day}
                onPickRecipe={() => setPickerDate(day.date)}
                onClearRecipe={() =>
                  saveDay(day.date, {
                    recipe_id: null,
                    free_text: null,
                    checked: false,
                    servings: null,
                  })
                }
                onSaveFreeText={(text) =>
                  saveDay(day.date, {
                    free_text: text === '' ? null : text,
                    recipe_id: null,
                    servings: null,
                  })
                }
                onToggleChecked={() => saveDay(day.date, { checked: !day.checked })}
                onChangeServings={(servings) => saveDay(day.date, { servings })}
              />
            ))}
          </div>
        ))}

      {pickerDate && (
        <RecipePickerModal
          onClose={() => setPickerDate(null)}
          onSelect={(recipe: RecipeListItem) => {
            saveDay(pickerDate, {
              recipe_id: recipe.id,
              free_text: null,
              servings: recipe.servings,
            })
            setPickerDate(null)
          }}
        />
      )}
    </div>
  )
}

function DayRow({
  day,
  onPickRecipe,
  onClearRecipe,
  onSaveFreeText,
  onToggleChecked,
  onChangeServings,
}: {
  day: WeekPlanDay
  onPickRecipe: () => void
  onClearRecipe: () => void
  onSaveFreeText: (text: string) => void
  onToggleChecked: () => void
  onChangeServings: (servings: number) => void
}) {
  const [text, setText] = useState(day.free_text ?? '')
  useEffect(() => setText(day.free_text ?? ''), [day.free_text])

  const hasContent = day.recipe_id !== null || Boolean(day.free_text?.trim())

  function commitText() {
    const trimmed = text.trim()
    if (trimmed === (day.free_text ?? '')) return
    onSaveFreeText(trimmed)
  }

  return (
    <div className="rounded-2xl border border-edge bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium capitalize">
          {weekdayFmt.format(fromIso(day.date))}{' '}
          <span className="font-normal text-ink-3">{shortDateFmt.format(fromIso(day.date))}</span>
        </span>
        {hasContent && (
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            <input
              type="checkbox"
              checked={day.checked}
              onChange={onToggleChecked}
              className="size-4 rounded border-edge accent-accent"
            />
            Afgevinkt
          </label>
        )}
      </div>

      <div className="mt-2">
        {day.recipe_id !== null ? (
          <div className="flex items-center gap-3 rounded-lg bg-raised p-2">
            <Link
              to={`/weekmenu/recepten/${day.recipe_id}`}
              className="flex min-w-0 flex-1 items-center gap-3"
            >
              {day.recipe_photo_path ? (
                <img
                  src={photoUrl(day.recipe_photo_path)}
                  alt=""
                  className="size-10 shrink-0 rounded-md object-cover"
                />
              ) : (
                <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-page text-ink-3">
                  <IconUtensils className="size-4" />
                </div>
              )}
              <span className="min-w-0 flex-1 truncate text-sm hover:underline">
                {day.recipe_title}
              </span>
            </Link>
            <button
              onClick={onPickRecipe}
              aria-label="Ander recept kiezen"
              className="shrink-0 rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-page hover:text-ink-2"
            >
              <IconSwap className="size-4" />
            </button>
            <div className="flex shrink-0 items-center gap-1 rounded-md bg-page px-1">
              <button
                onClick={() => onChangeServings(Math.max(1, (day.servings ?? 1) - 1))}
                aria-label="Minder personen"
                className="flex size-6 items-center justify-center rounded text-ink-3 transition-colors hover:bg-surface hover:text-ink-2 disabled:opacity-40"
                disabled={(day.servings ?? 1) <= 1}
              >
                −
              </button>
              <span className="min-w-4 text-center text-xs tabular-nums text-ink-2">
                {day.servings ?? 1}
              </span>
              <button
                onClick={() => onChangeServings((day.servings ?? 1) + 1)}
                aria-label="Meer personen"
                className="flex size-6 items-center justify-center rounded text-ink-3 transition-colors hover:bg-surface hover:text-ink-2"
              >
                +
              </button>
            </div>
            <button
              onClick={onClearRecipe}
              aria-label="Recept verwijderen"
              className="shrink-0 rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-page hover:text-ink-2"
            >
              <IconTrash className="size-4" />
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={onPickRecipe} className={secondaryButtonClass}>
              + Recept
            </button>
            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onBlur={commitText}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur()
              }}
              placeholder="Of typ vrije tekst…"
              className={`${inputClass} max-w-xs flex-1`}
            />
          </div>
        )}
      </div>
    </div>
  )
}
