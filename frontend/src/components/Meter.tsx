// Meter volgens de dataviz-spec: de vulling draagt de status, de lege track is
// dezelfde tint op lage dekking (blauw-op-blauw), zodat de hele balk als één
// systeem leest. Status komt nooit uit kleur alleen — de rijtekst ernaast
// benoemt de toestand.

export type MeterTone = 'accent' | 'good' | 'warn' | 'crit'

const TONE_HEX: Record<MeterTone, string> = {
  accent: '#3987e5',
  good: '#0ca30c',
  warn: '#fab219',
  crit: '#d03b3b',
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
      style={{ backgroundColor: `${hex}2e` }}
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

/** Statuslogica voor uitgaven-categorieën: onder 85 % rustig, dan waarschuwing, boven budget kritiek. */
export function spendingTone(actual: number, budget: number): MeterTone {
  if (budget <= 0) return actual > 0 ? 'crit' : 'accent'
  const fraction = actual / budget
  if (fraction > 1) return 'crit'
  if (fraction >= 0.85) return 'warn'
  return 'accent'
}

/** Inkomen/Sparen: doel gehaald is goed nieuws. */
export function fundingTone(actual: number, budget: number): MeterTone {
  return budget > 0 && actual >= budget ? 'good' : 'accent'
}
