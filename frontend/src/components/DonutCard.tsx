// Ringdiagram per type, zoals de "Categories (Tracked)"-donuts in de Excel:
// segmenten in tinten van de typekleur (donkerste = grootste), top 5 +
// "Overige", legend met bedragen en het totaal onderaan.

import { useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { OTHER_HEX, RAMPS } from '../lib/chartColors'
import { formatCents } from '../lib/format'
import { useChartPress } from '../lib/useChartPress'

const TOP_N = 5
const pctFmt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 1 })

export interface DonutRow {
  name: string
  cents: number
  /** Vaste categorische kleur (kleur volgt de entiteit); anders de type-ramp. */
  color?: string
}

interface DonutCardProps {
  title: string
  rows: DonutRow[]
  /** Sequentiële ramp wanneer de rijen zelf geen kleur dragen. */
  kind?: keyof typeof RAMPS
  /** Aantal losse segmenten voor "Overige" (default 5). */
  maxSegments?: number
  /** Optionele bijschrift onder de titel. */
  subtitle?: string
  /** Tailwind-maat van de ring (default h-36 w-36). */
  ringClass?: string
}

export default function DonutCard({
  title,
  kind,
  rows,
  maxSegments = TOP_N,
  subtitle,
  ringClass = 'h-36 w-36',
}: DonutCardProps) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  // Op mobiel toont de ring z'n tooltip enkel zolang je erop duwt (press-to-show);
  // de legende hieronder heeft alle bedragen/percentages toch al staan.
  const { tooltipActive, pressHandlers } = useChartPress()
  const sorted = rows.filter((r) => r.cents > 0).sort((a, b) => b.cents - a.cents)
  const top = sorted.slice(0, maxSegments)
  const restCents = sorted.slice(maxSegments).reduce((sum, r) => sum + r.cents, 0)
  const ramp = kind ? RAMPS[kind] : []
  const segments = [
    ...top.map((r, i) => ({ ...r, color: r.color ?? ramp[i] ?? OTHER_HEX })),
    ...(restCents > 0 ? [{ name: 'Overige', cents: restCents, color: OTHER_HEX }] : []),
  ]
  // Klikken in de legende verbergt een segment; ring en totaal rekenen op de rest.
  const shown = segments.filter((s) => !hidden.has(s.name))
  const total = shown.reduce((sum, s) => sum + s.cents, 0)
  // Percentage per rij t.o.v. het volledige totaal (stabiel, telt op tot 100 %).
  const segTotal = segments.reduce((sum, s) => sum + s.cents, 0)

  function toggle(name: string) {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  return (
    <div className="flex min-w-0 flex-col rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium text-ink-2">{title}</h3>
      {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
      {segments.length === 0 ? (
        <p className="flex flex-1 items-center justify-center py-10 text-sm text-ink-3">
          Geen bedragen in deze periode
        </p>
      ) : (
        // Op smalle schermen ring boven de legende — naast elkaar past niet in 390px.
        <div className="mt-3 flex flex-1 items-center gap-5 max-md:flex-col max-md:gap-4">
          <div className={`${ringClass} shrink-0`}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart {...pressHandlers}>
                <Pie
                  data={shown}
                  dataKey="cents"
                  nameKey="name"
                  innerRadius="62%"
                  outerRadius="100%"
                  paddingAngle={1}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {shown.map((s) => (
                    <Cell key={s.name} fill={s.color} />
                  ))}
                </Pie>
                <Tooltip
                  active={tooltipActive}
                  formatter={(value) => formatCents(value as number)}
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid rgb(11 11 11 / 0.1)',
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="min-w-0 flex-1 max-md:w-full">
            <ul className="space-y-1.5 text-sm">
              {segments.map((s) => {
                const off = hidden.has(s.name)
                return (
                  <li key={s.name}>
                    <button
                      type="button"
                      onClick={() => toggle(s.name)}
                      aria-pressed={!off}
                      className={`flex w-full items-center gap-2 text-left transition-opacity ${
                        off ? 'opacity-40' : ''
                      }`}
                    >
                      <span
                        aria-hidden
                        className="size-2.5 shrink-0 rounded-sm"
                        style={{ backgroundColor: s.color }}
                      />
                      <span className={`min-w-0 flex-1 truncate text-ink-2 ${off ? 'line-through' : ''}`}>
                        {s.name}
                      </span>
                      <span className="flex shrink-0 items-baseline gap-1 tabular-nums">
                        <span>{formatCents(s.cents)}</span>
                        {segTotal > 0 && (
                          <span className="w-14 text-right text-xs text-ink-3">
                            ({pctFmt.format((s.cents / segTotal) * 100)} %)
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
            <p className="mt-3 flex items-center border-t border-line pt-2 text-sm font-medium">
              Totaal
              <span className="ml-auto tabular-nums">{formatCents(total)}</span>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
