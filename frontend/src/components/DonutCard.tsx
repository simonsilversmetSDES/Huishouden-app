// Ringdiagram per type, zoals de "Categories (Tracked)"-donuts in de Excel:
// segmenten in tinten van de typekleur (donkerste = grootste), top 5 +
// "Overige", legend met bedragen en het totaal onderaan.

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { OTHER_HEX, RAMPS } from '../lib/chartColors'
import { formatCents } from '../lib/format'

const TOP_N = 5

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
}

export default function DonutCard({ title, kind, rows, maxSegments = TOP_N }: DonutCardProps) {
  const sorted = rows.filter((r) => r.cents > 0).sort((a, b) => b.cents - a.cents)
  const top = sorted.slice(0, maxSegments)
  const restCents = sorted.slice(maxSegments).reduce((sum, r) => sum + r.cents, 0)
  const ramp = kind ? RAMPS[kind] : []
  const segments = [
    ...top.map((r, i) => ({ ...r, color: r.color ?? ramp[i] ?? OTHER_HEX })),
    ...(restCents > 0 ? [{ name: 'Overige', cents: restCents, color: OTHER_HEX }] : []),
  ]
  const total = segments.reduce((sum, s) => sum + s.cents, 0)

  return (
    <div className="flex flex-col rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium text-ink-2">{title}</h3>
      {segments.length === 0 ? (
        <p className="flex flex-1 items-center justify-center py-10 text-sm text-ink-3">
          Geen bedragen in deze periode
        </p>
      ) : (
        <div className="mt-3 flex flex-1 items-center gap-5">
          <div className="h-36 w-36 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={segments}
                  dataKey="cents"
                  nameKey="name"
                  innerRadius="62%"
                  outerRadius="100%"
                  paddingAngle={1}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {segments.map((s) => (
                    <Cell key={s.name} fill={s.color} />
                  ))}
                </Pie>
                <Tooltip
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
          <div className="min-w-0 flex-1">
            <ul className="space-y-1.5 text-sm">
              {segments.map((s) => (
                <li key={s.name} className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-sm"
                    style={{ backgroundColor: s.color }}
                  />
                  <span className="truncate text-ink-2">{s.name}</span>
                  <span className="ml-auto shrink-0 tabular-nums">{formatCents(s.cents)}</span>
                </li>
              ))}
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
