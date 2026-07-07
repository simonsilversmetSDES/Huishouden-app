// "Werkelijk vs. budget" per maand, zoals de Tracked (vs. Budget)-grafiek in de
// Excel: per type één gestapelde balk. De volle basis = min(werkelijk, budget);
// daarboven een donker segment als werkelijk het budget overschrijdt, of een
// lichte tint als er budget overblijft. De balk reikt dus tot max(werkelijk,
// budget). In maand-modus dimt de niet-gekozen maand; de legend schakelt types.

import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CategoryType, MonthTotals } from '../api/types'
import { RAMPS } from '../lib/chartColors'
import { formatCents, MAAND_KORT } from '../lib/format'

type RampKey = keyof typeof RAMPS

const SERIES: { type: CategoryType; key: RampKey }[] = [
  { type: 'Inkomen', key: 'income' },
  { type: 'Uitgaven', key: 'expense' },
  { type: 'Sparen', key: 'saving' },
]

// Per type: basis (mid), overschrijding (donkerst), resterend budget (licht).
function shades(key: RampKey) {
  return { base: RAMPS[key][1], over: RAMPS[key][0], under: RAMPS[key][3] }
}

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
    const row: Record<string, number> = { month: m.month }
    for (const { type } of SERIES) {
      const budget = byType.get(type)?.budget_cents ?? 0
      const actual = byType.get(type)?.actual_cents ?? 0
      row[`${type}_base`] = Math.min(actual, budget)
      row[`${type}_over`] = Math.max(actual - budget, 0)
      row[`${type}_under`] = Math.max(budget - actual, 0)
    }
    return { ...row, label: MAAND_KORT[m.month - 1] }
  })

  const dimmed = (month: number) => selectedMonth !== null && month !== selectedMonth
  const opacity = (month: number) => (dimmed(month) ? 0.25 : 1)

  return (
    <div className="flex flex-col rounded-2xl border border-edge bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-ink-2">Werkelijk vs. budget</h3>
        <div className="ml-auto flex gap-3">
          {SERIES.map(({ type, key }) => (
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
                style={{ backgroundColor: shades(key).base }}
              />
              {type}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barCategoryGap="12%" barGap={2}>
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
              formatter={(value, name) => [formatCents(value as number), name]}
              contentStyle={{
                backgroundColor: '#ffffff',
                border: '1px solid rgb(11 11 11 / 0.1)',
                borderRadius: 12,
                fontSize: 12,
              }}
            />
            {SERIES.filter(({ type }) => visible[type]).flatMap(({ type, key }) => {
              const s = shades(key)
              return [
                <Bar key={`${type}_base`} dataKey={`${type}_base`} stackId={type} name={type} fill={s.base}>
                  {data.map((_, i) => (
                    <Cell key={i} fillOpacity={opacity(months[i].month)} />
                  ))}
                </Bar>,
                <Bar
                  key={`${type}_over`}
                  dataKey={`${type}_over`}
                  stackId={type}
                  name={`${type} · boven budget`}
                  fill={s.over}
                >
                  {data.map((_, i) => (
                    <Cell key={i} fillOpacity={opacity(months[i].month)} />
                  ))}
                </Bar>,
                <Bar
                  key={`${type}_under`}
                  dataKey={`${type}_under`}
                  stackId={type}
                  name={`${type} · resterend budget`}
                  fill={s.under}
                >
                  {data.map((_, i) => (
                    <Cell key={i} fillOpacity={opacity(months[i].month)} />
                  ))}
                </Bar>,
              ]
            })}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
