// Periode-keuze zoals in de oude Excel: een losse maand of het hele jaar
// ("Total Year"), met ‹ ›-navigatie binnen de gekozen modus.

export interface Period {
  mode: 'maand' | 'jaar'
  year: number
  month: number
}

export function currentPeriod(mode: Period['mode'] = 'maand'): Period {
  const now = new Date()
  return { mode, year: now.getFullYear(), month: now.getMonth() + 1 }
}

export function shiftPeriod(period: Period, delta: number): Period {
  if (period.mode === 'jaar') return { ...period, year: period.year + delta }
  const index = period.year * 12 + (period.month - 1) + delta
  return { ...period, year: Math.floor(index / 12), month: (index % 12) + 1 }
}

export function isCurrentPeriod(period: Period): boolean {
  const now = currentPeriod(period.mode)
  return period.year === now.year && (period.mode === 'jaar' || period.month === now.month)
}

interface PeriodPickerProps {
  period: Period
  onChange: (period: Period) => void
}

export default function PeriodPicker({ period, onChange }: PeriodPickerProps) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex rounded-lg border border-edge bg-surface p-0.5">
        {(['maand', 'jaar'] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => onChange({ ...period, mode })}
            className={`rounded-md px-3 py-1 text-sm capitalize transition-colors ${
              period.mode === mode
                ? 'bg-raised font-medium text-ink'
                : 'text-ink-3 hover:text-ink-2'
            }`}
          >
            {mode}
          </button>
        ))}
      </div>
      {!isCurrentPeriod(period) && (
        <button
          onClick={() => onChange(currentPeriod(period.mode))}
          className="rounded-lg px-2.5 py-1.5 text-sm text-ink-3 hover:bg-raised hover:text-ink-2"
        >
          Vandaag
        </button>
      )}
      <button
        onClick={() => onChange(shiftPeriod(period, -1))}
        aria-label={period.mode === 'jaar' ? 'Vorig jaar' : 'Vorige maand'}
        className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
      >
        ‹
      </button>
      <button
        onClick={() => onChange(shiftPeriod(period, 1))}
        aria-label={period.mode === 'jaar' ? 'Volgend jaar' : 'Volgende maand'}
        className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
      >
        ›
      </button>
    </div>
  )
}
