import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PortfolioHistory } from '../api/types'
import { MAAND_KORT, formatCents, formatCentsWhole, formatDate } from '../lib/format'
import { useChartPress } from '../lib/useChartPress'
import { useCoarsePointer } from '../lib/useMediaQuery'

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

  // Gekozen tijdsvenster als [start, eind]-index in `data`; null = volledige periode.
  // Zowel de sleep-selectie op de grafiek als de schuifbalk onderaan sturen dit aan.
  const [range, setRange] = useState<[number, number] | null>(null)
  // Sleep-in-uitvoering op het grafiekvlak (in `i`-waarden, dus absolute indexen).
  const coarse = useCoarsePointer()
  // Op mobiel: tooltip enkel tonen zolang je op de grafiek duwt.
  const { tooltipActive, pressHandlers } = useChartPress()
  const [dragStart, setDragStart] = useState<number | null>(null)
  const [dragEnd, setDragEnd] = useState<number | null>(null)

  // Verandert de reeks (ander effect aangevinkt) → venster terug naar volledig.
  useEffect(() => setRange(null), [data.length])

  // Snelkoppelingen: laatste 6 maanden / 1 jaar / 3 jaar t.o.v. het recentste punt.
  // Enkel tonen wat de reeks effectief inkort (start > 0); "Alles" staat er los bij.
  const presets = useMemo(() => {
    if (data.length === 0) return [] as { label: string; start: number }[]
    const last = new Date(data[data.length - 1].date)
    const out: { label: string; start: number }[] = []
    for (const { label, months } of [
      { label: '6M', months: 6 },
      { label: '1J', months: 12 },
      { label: '3J', months: 36 },
    ]) {
      const cutoff = new Date(last)
      cutoff.setMonth(cutoff.getMonth() - months)
      const start = data.findIndex((r) => new Date(r.date) >= cutoff)
      if (start > 0) out.push({ label, start })
    }
    return out
  }, [data])

  const maxIdx = Math.max(0, data.length - 1)
  const startIndex = range ? Math.min(range[0], maxIdx) : 0
  const endIndex = range ? Math.min(range[1], maxIdx) : maxIdx

  // Compacte datumlabels onder de schuifbalk (bv. "mrt '25").
  const brushLabel = (i: number) => {
    const row = data[i]
    if (!row) return ''
    const d = new Date(row.date)
    return `${MAAND_KORT[d.getMonth()]} '${String(d.getFullYear()).slice(2)}`
  }

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
          {presets.length > 0 && (
            <div className="inline-flex rounded-lg border border-edge p-0.5 font-medium">
              {presets.map((p) => {
                const on = range !== null && range[0] === p.start && range[1] === maxIdx
                return (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => setRange([p.start, maxIdx])}
                    aria-pressed={on}
                    className={`rounded-md px-2 py-0.5 transition-colors ${
                      on ? 'bg-accent text-white' : 'text-ink-3 hover:text-ink-2'
                    }`}
                  >
                    {p.label}
                  </button>
                )
              })}
              <button
                type="button"
                onClick={() => setRange(null)}
                aria-pressed={range === null}
                className={`rounded-md px-2 py-0.5 transition-colors ${
                  range === null ? 'bg-accent text-white' : 'text-ink-3 hover:text-ink-2'
                }`}
              >
                Alles
              </button>
            </div>
          )}
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

      <div className="mt-4 h-80 touch-pan-y max-md:h-64">
        {history === null ? (
          <p className="flex h-full items-center justify-center text-sm text-ink-3">Laden…</p>
        ) : data.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-ink-3">
            Vink minstens één effect aan om de grafiek te tonen.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={data}
              margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
              {...pressHandlers}
              // Sleep-zoom is muiswerk; op touch moet slepen de pagina scrollen.
              style={coarse ? undefined : { cursor: 'crosshair' }}
              onMouseDown={(s) => {
                if (coarse) return
                const i = Number(s?.activeLabel)
                if (!Number.isNaN(i)) {
                  setDragStart(i)
                  setDragEnd(i)
                }
              }}
              onMouseMove={(s) => {
                if (dragStart === null) return
                const i = Number(s?.activeLabel)
                if (!Number.isNaN(i)) setDragEnd(i)
              }}
              onMouseUp={() => {
                if (dragStart !== null && dragEnd !== null && dragStart !== dragEnd) {
                  setRange(dragStart < dragEnd ? [dragStart, dragEnd] : [dragEnd, dragStart])
                }
                setDragStart(null)
                setDragEnd(null)
              }}
              onMouseLeave={() => {
                setDragStart(null)
                setDragEnd(null)
              }}
              onDoubleClick={() => {
                setRange(null)
                setDragStart(null)
                setDragEnd(null)
              }}
            >
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
                active={tooltipActive}
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
              {/* Blauwe zone tijdens het slepen om een periode te selecteren. */}
              {dragStart !== null && dragEnd !== null && dragStart !== dragEnd && (
                <ReferenceArea
                  x1={Math.min(dragStart, dragEnd)}
                  x2={Math.max(dragStart, dragEnd)}
                  fill={WAARDE}
                  fillOpacity={0.08}
                  stroke={WAARDE}
                  strokeOpacity={0.3}
                />
              )}
              {/* Schuifbalk onderaan: sleep de handvatten of de balk om de periode aan te passen. */}
              <Brush
                dataKey="i"
                height={26}
                travellerWidth={8}
                gap={1}
                stroke="#b8b7b0"
                fill="rgba(11, 11, 11, 0.02)"
                tickFormatter={(i: number) => brushLabel(i)}
                startIndex={startIndex}
                endIndex={endIndex}
                onChange={(r) => {
                  if (
                    typeof r.startIndex === 'number' &&
                    typeof r.endIndex === 'number' &&
                    (r.startIndex !== 0 || r.endIndex !== maxIdx)
                  ) {
                    setRange([r.startIndex, r.endIndex])
                  } else {
                    setRange(null)
                  }
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}
