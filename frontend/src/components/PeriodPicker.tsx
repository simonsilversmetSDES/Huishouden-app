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

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
const monthFmt = new Intl.DateTimeFormat('nl-BE', { month: 'long' })

function monthLabel(month: number): string {
  const name = monthFmt.format(new Date(2000, month - 1, 1))
  return name.charAt(0).toUpperCase() + name.slice(1)
}

// Maand kiezen via dropdown (12 maanden + "Volledig jaar"); de ‹ ›-pijltjes
// verschuiven de periode één stap (maand in maand-modus, jaar in jaar-modus,
// telkens met jaarovergang). "Volledig jaar" = de jaar-modus.
export default function PeriodPicker({ period, onChange }: PeriodPickerProps) {
  const stepLabel = period.mode === 'jaar' ? 'jaar' : 'maand'
  return (
    <div className="flex items-center gap-1.5">
      <select
        aria-label="Maand"
        value={period.mode === 'jaar' ? 'jaar' : String(period.month)}
        onChange={(e) => {
          const value = e.target.value
          onChange(
            value === 'jaar'
              ? { ...period, mode: 'jaar' }
              : { ...period, mode: 'maand', month: Number(value) },
          )
        }}
        className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 focus:border-accent focus:outline-none"
      >
        {MONTHS.map((m) => (
          <option key={m} value={m}>
            {monthLabel(m)}
          </option>
        ))}
        <option value="jaar">Volledig jaar</option>
      </select>
      {!isCurrentPeriod(period) && (
        <button
          onClick={() => onChange(currentPeriod(period.mode))}
          className="rounded-lg px-2.5 py-1.5 text-sm text-ink-3 hover:bg-raised hover:text-ink-2"
        >
          Vandaag
        </button>
      )}
      <div className="flex items-center gap-1">
        <button
          onClick={() => onChange(shiftPeriod(period, -1))}
          aria-label={`Vorige ${stepLabel}`}
          className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
        >
          ‹
        </button>
        <span className="min-w-[4ch] text-center text-sm font-medium tabular-nums text-ink-2">
          {period.year}
        </span>
        <button
          onClick={() => onChange(shiftPeriod(period, 1))}
          aria-label={`Volgende ${stepLabel}`}
          className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
        >
          ›
        </button>
      </div>
    </div>
  )
}
