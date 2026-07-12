import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PortfolioHistory } from '../api/types'
import { MAAND_KORT, formatCents, formatCentsWhole, formatDate } from '../lib/format'

// Huisstijl-typekleuren (index.css): waarde = sparen-blauw, inleg = uitgaven-oranje
// (wat je erin stak). Paar gevalideerd op CVD-afstand en contrast op wit.
const WAARDE = '#2a78d6'
const INLEG = '#eb6834'

interface Row {
  i: number
  date: string // ISO
  cost: number // inleg in centen (som van de aangevinkte effecten)
  value: number | null // waarde in centen; null zolang een positie geen koers heeft
}

/** Groepssleutel + aslabel: per jaar bij een lange reeks, anders per maand
 * (januari toont het jaartal, zodat de maanden een anker hebben). */
function tickOf(d: Date, spanDays: number): { key: string; label: string } {
  if (spanDays > 3 * 365) return { key: `${d.getFullYear()}`, label: `${d.getFullYear()}` }
  return {
    key: `${d.getFullYear()}-${d.getMonth()}`,
    label: d.getMonth() === 0 ? `${d.getFullYear()}` : MAAND_KORT[d.getMonth()],
  }
}

function HistoryTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { payload: Row }[]
}) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0].payload
  const gain = row.value !== null ? row.value - row.cost : null
  return (
    <div className="min-w-44 rounded-xl border border-edge bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="font-medium">{formatDate(row.date)}</p>
      <div className="mt-1 space-y-0.5 tabular-nums">
        <p className="flex items-center gap-1.5">
          <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: WAARDE }} />
          <span className="text-ink-2">Waarde</span>
          <span className="ml-auto pl-3 font-medium">
            {row.value !== null ? formatCents(row.value) : 'geen koers'}
          </span>
        </p>
        <p className="flex items-center gap-1.5">
          <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: INLEG }} />
          <span className="text-ink-2">Inleg</span>
          <span className="ml-auto pl-3 font-medium">{formatCents(row.cost)}</span>
        </p>
      </div>
      {gain !== null && (
        <p className="mt-1 flex items-center border-t border-line pt-1 tabular-nums">
          <span className="text-ink-2">Winst/verlies</span>
          <span
            className={`ml-auto pl-3 font-medium ${gain < 0 ? 'text-crit' : 'text-good'}`}
          >
            {gain > 0 ? '+' : ''}
            {formatCents(gain)}
          </span>
        </p>
      )}
    </div>
  )
}

export default function PortfolioHistoryChart({
  history,
  selected,
}: {
  history: PortfolioHistory | null
  selected: Set<number>
}) {
  const { data, ticks, labels } = useMemo(() => {
    const none = { data: [] as Row[], ticks: [] as number[], labels: [] as string[] }
    if (!history || history.dates.length === 0) return none
    const series = history.series.filter((s) => selected.has(s.security_id))
    const rows = history.dates.map((date, i) => {
      let cost = 0
      let value: number | null = 0
      for (const s of series) {
        cost += s.points[i].cost_cents
        const v = s.points[i].value_cents
        value = v === null || value === null ? null : value + v
      }
      return { date, cost, value }
    })
    // Vlakke nul-aanloop weglaten (de selectie kan pas later gekocht zijn).
    const startIdx = rows.findIndex((r) => r.cost !== 0 || (r.value ?? 0) !== 0)
    if (startIdx === -1) return none
    const data: Row[] = rows.slice(startIdx).map((r, i) => ({ ...r, i }))

    const spanDays =
      (new Date(data[data.length - 1].date).getTime() - new Date(data[0].date).getTime()) /
      86_400_000
    const keys = data.map((r) => tickOf(new Date(r.date), spanDays))
    let ticks = data
      .filter((r) => r.i === 0 || keys[r.i].key !== keys[r.i - 1].key)
      .map((r) => r.i)
    if (ticks.length > 10) {
      const step = Math.ceil(ticks.length / 10)
      ticks = ticks.filter((_, n) => n % step === 0)
    }
    return { data, ticks, labels: keys.map((k) => k.label) }
  }, [history, selected])

  // Geen enkele transactie in de hele portefeuille → niets te tonen.
  if (history !== null && history.series.length === 0) return null

  return (
    <section className="rounded-2xl border border-edge bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="text-base font-medium">Waarde t.o.v. inleg</h2>
          <span className="text-xs text-ink-3">
            volgt de aangevinkte effecten — het gat tussen de lijnen is de winst of het verlies
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-ink-2">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded-full" style={{ backgroundColor: WAARDE }} />
            Waarde
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded-full" style={{ backgroundColor: INLEG }} />
            Inleg
          </span>
        </div>
      </div>

      <div className="mt-4 h-72">
        {history === null ? (
          <p className="flex h-full items-center justify-center text-sm text-ink-3">Laden…</p>
        ) : data.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-ink-3">
            Vink minstens één effect aan om de grafiek te tonen.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="portfolioValueFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={WAARDE} stopOpacity={0.14} />
                  <stop offset="100%" stopColor={WAARDE} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="#e1e0d9" />
              <XAxis
                dataKey="i"
                type="category"
                ticks={ticks}
                tickFormatter={(i: number) => labels[i] ?? ''}
                tickLine={false}
                axisLine={{ stroke: '#e1e0d9' }}
                tick={{ fill: '#898781', fontSize: 11 }}
              />
              <YAxis
                domain={[0, 'auto']}
                tickLine={false}
                axisLine={false}
                width={72}
                tick={{ fill: '#898781', fontSize: 11 }}
                tickFormatter={(v: number) => `€ ${formatCentsWhole(v)}`}
              />
              <Tooltip
                cursor={{ stroke: '#898781', strokeDasharray: '4 3' }}
                content={<HistoryTooltip />}
              />
              <Area
                type="linear"
                dataKey="value"
                stroke={WAARDE}
                strokeWidth={2}
                fill="url(#portfolioValueFill)"
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
              {/* stepAfter: de inleg verspringt op transactiedatums, tussenin is ze vlak */}
              <Line
                type="stepAfter"
                dataKey="cost"
                stroke={INLEG}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}
