// "Werkelijk vs. budget" per maand, zoals de Tracked (vs. Budget)-grafiek in
// de Excel: per type een paar staven (budget in lichte tint, werkelijk vol).
// In maand-modus is de gekozen maand vol gekleurd en de rest gedimd; de legend
// schakelt series aan/uit (de Excel-checkboxes).

import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CategoryType, MonthTotals } from '../api/types'
import { formatCents, MAAND_KORT } from '../lib/format'
import { TONE_HEX } from './Meter'

const SERIES: { type: CategoryType; hex: string }[] = [
  { type: 'Inkomen', hex: TONE_HEX.income },
  { type: 'Uitgaven', hex: TONE_HEX.expense },
  { type: 'Sparen', hex: TONE_HEX.saving },
]

const euroInt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 0 })

interface TrackedVsBudgetProps {
  months: MonthTotals[]
  /** In maand-modus: de gekozen maand (1–12); de andere maanden dimmen. */
  selectedMonth: number | null
}

export default function TrackedVsBudget({ months, selectedMonth }: TrackedVsBudgetProps) {
  const [visible, setVisible] = useState<Record<CategoryType, boolean>>({
    Inkomen: true,
    Uitgaven: true,
    Sparen: true,
  })

  const data = months.map((m) => {
    const byType = new Map(m.totals.map((t) => [t.type, t]))
    return {
      month: m.month,
      label: MAAND_KORT[m.month - 1],
      ...Object.fromEntries(
        SERIES.flatMap(({ type }) => [
          [`${type}_budget`, byType.get(type)?.budget_cents ?? 0],
          [`${type}_werkelijk`, byType.get(type)?.actual_cents ?? 0],
        ]),
      ),
    }
  })

  const dimmed = (month: number) => selectedMonth !== null && month !== selectedMonth

  return (
    <div className="flex flex-col rounded-2xl border border-edge bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-ink-2">Werkelijk vs. budget</h3>
        <div className="ml-auto flex gap-3">
          {SERIES.map(({ type, hex }) => (
            <button
              key={type}
              onClick={() => setVisible((v) => ({ ...v, [type]: !v[type] }))}
              aria-pressed={visible[type]}
              className={`flex items-center gap-1.5 text-xs transition-opacity ${
                visible[type] ? 'text-ink-2' : 'opacity-40'
              }`}
            >
              <span
                aria-hidden
                className="size-2.5 rounded-sm"
                style={{ backgroundColor: hex }}
              />
              {type}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barCategoryGap="22%" barGap={1}>
            <CartesianGrid vertical={false} stroke="#e1e0d9" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={{ stroke: '#e1e0d9' }}
              tick={{ fill: '#898781', fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={48}
              tick={{ fill: '#898781', fontSize: 11 }}
              tickFormatter={(cents: number) => euroInt.format(cents / 100)}
            />
            <Tooltip
              cursor={{ fill: 'rgb(11 11 11 / 0.04)' }}
              formatter={(value) => formatCents(value as number)}
              contentStyle={{
                backgroundColor: '#ffffff',
                border: '1px solid rgb(11 11 11 / 0.1)',
                borderRadius: 12,
                fontSize: 12,
              }}
            />
            {SERIES.filter(({ type }) => visible[type]).flatMap(({ type, hex }) => [
              <Bar key={`${type}_budget`} dataKey={`${type}_budget`} name={`${type} (budget)`} fill={hex}>
                {data.map((d) => (
                  <Cell key={d.month} fillOpacity={dimmed(d.month) ? 0.08 : 0.25} />
                ))}
              </Bar>,
              <Bar
                key={`${type}_werkelijk`}
                dataKey={`${type}_werkelijk`}
                name={`${type} (werkelijk)`}
                fill={hex}
              >
                {data.map((d) => (
                  <Cell key={d.month} fillOpacity={dimmed(d.month) ? 0.3 : 1} />
                ))}
              </Bar>,
            ])}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
