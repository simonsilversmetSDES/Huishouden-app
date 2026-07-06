// Meter volgens de dataviz-spec: de vulling draagt de betekenis, de lege track
// is dezelfde tint op lage dekking. De typekleuren volgen de oude Excel
// (Inkomen groen, Uitgaven oranje, Sparen blauw); status komt nooit uit kleur
// alleen — de tekst ernaast benoemt de toestand.

export type MeterTone = 'income' | 'expense' | 'saving' | 'accent' | 'good' | 'warn' | 'crit'

export const TONE_HEX: Record<MeterTone, string> = {
  income: '#008300',
  expense: '#eb6834',
  saving: '#2a78d6',
  accent: '#2a78d6',
  good: '#008300',
  warn: '#d97706',
  crit: '#c62828',
}

interface MeterProps {
  /** Werkelijk bedrag (centen). */
  value: number
  /** Budget (centen); 0 = geen budget, toont een lege track. */
  max: number
  tone: MeterTone
}

export default function Meter({ value, max, tone }: MeterProps) {
  const fraction = max > 0 ? Math.min(value / max, 1) : 0
  const hex = TONE_HEX[tone]
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full"
      style={{ backgroundColor: `${hex}26` }}
    >
      <div
        className="h-full rounded-full transition-[width] duration-300"
        style={{
          width: `${fraction * 100}%`,
          minWidth: value > 0 && fraction > 0 ? 2 : 0,
          backgroundColor: hex,
        }}
      />
    </div>
  )
}

/** Uitgaven: binnen budget in de typekleur, boven budget kritiek. */
export function spendingTone(actual: number, budget: number): MeterTone {
  if (budget <= 0) return actual > 0 ? 'crit' : 'expense'
  return actual > budget ? 'crit' : 'expense'
}
