import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, ApiError } from '../api/client'
import type { ChartRange, PriceHistory } from '../api/types'
import { useChartPress } from '../lib/useChartPress'
import { useCoarsePointer } from '../lib/useMediaQuery'

// Dezelfde tijdsblokken als Yahoo Finance; het interval kiest de backend.
const RANGES: { key: ChartRange; label: string }[] = [
  { key: '1d', label: '1D' },
  { key: '5d', label: '5D' },
  { key: '1mo', label: '1M' },
  { key: '6mo', label: '6M' },
  { key: 'ytd', label: 'YTD' },
  { key: '1y', label: '1J' },
  { key: '5y', label: '5J' },
  { key: 'max', label: 'MAX' },
]

const priceFmt = new Intl.NumberFormat('nl-BE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const pctFmt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 2 })
const timeFmt = new Intl.DateTimeFormat('nl-BE', { hour: '2-digit', minute: '2-digit' })
const dayFmt = new Intl.DateTimeFormat('nl-BE', { day: '2-digit', month: '2-digit' })
const dateFmt = new Intl.DateTimeFormat('nl-BE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})
const monthFmt = new Intl.DateTimeFormat('nl-BE', { month: 'short' })

/** Groepssleutel voor de X-as: per uur (1D), dag (5D), week (1M), maand of jaar. */
function tickKey(d: Date, range: ChartRange): string {
  if (range === '1d') return `${d.getHours()}`
  if (range === '5d') return d.toDateString()
  if (range === '1mo') return `${Math.floor(d.getTime() / (7 * 86_400_000))}` // per week
  if (range === '5y' || range === 'max') return `${d.getFullYear()}`
  return `${d.getFullYear()}-${d.getMonth()}` // 6mo / ytd / 1y: per maand
}

function tickLabel(d: Date, range: ChartRange): string {
  if (range === '1d') return timeFmt.format(d)
  if (range === '5d' || range === '1mo') return dayFmt.format(d)
  if (range === '5y' || range === 'max') return `${d.getFullYear()}`
  return monthFmt.format(d)
}

/** Tooltip-label: intraday met uur, anders enkel de datum. */
function tooltipLabel(d: Date, range: ChartRange): string {
  if (range === '1d' || range === '5d') return `${dateFmt.format(d)} ${timeFmt.format(d)}`
  return dateFmt.format(d)
}

export default function PriceChartModal({
  securityId,
  name,
  ticker,
  onClose,
}: {
  securityId: number
  name: string
  ticker: string
  onClose: () => void
}) {
  const [range, setRange] = useState<ChartRange>('1d')
  const [history, setHistory] = useState<PriceHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false
    setLoading(true)
    setError(null)
    api<PriceHistory>(`/api/securities/${securityId}/history?range=${range}`)
      .then((res) => {
        if (!stale) setHistory(res)
      })
      .catch((err) => {
        if (stale) return
        setError(
          err instanceof ApiError && err.status === 503
            ? 'Koersen ophalen is uitgeschakeld (price_fetch_enabled).'
            : 'Koershistoriek ophalen mislukt — probeer opnieuw.',
        )
      })
      .finally(() => {
        if (!stale) setLoading(false)
      })
    return () => {
      stale = true
    }
  }, [securityId, range])

  // Reeks voor recharts + de as-ticks (eerste punt van elk uur/dag/maand/jaar).
  const { data, ticks } = useMemo(() => {
    if (!history || history.range !== range) return { data: [], ticks: [] as number[] }
    const rows = history.points.map((p, i) => {
      const d = new Date(p.t)
      return { i, price: Number(p.price), label: tickLabel(d, range), tooltip: tooltipLabel(d, range), key: tickKey(d, range) }
    })
    let tickIdx = rows.filter((r, i) => i === 0 || r.key !== rows[i - 1].key).map((r) => r.i)
    if (tickIdx.length > 10) {
      const step = Math.ceil(tickIdx.length / 10)
      tickIdx = tickIdx.filter((_, i) => i % step === 0)
    }
    return { data: rows, ticks: tickIdx }
  }, [history, range])

  // Ingezoomd venster als [start, eind]-index; null = volledige periode. Sleep-
  // selectie op de grafiek én de schuifbalk onderaan sturen dit aan.
  const coarse = useCoarsePointer()
  // Op mobiel: tooltip enkel tonen zolang je op de grafiek duwt.
  const { tooltipActive, pressHandlers } = useChartPress()
  const [zoom, setZoom] = useState<[number, number] | null>(null)
  const [dragStart, setDragStart] = useState<number | null>(null)
  const [dragEnd, setDragEnd] = useState<number | null>(null)

  // Andere periode gekozen (nieuwe reeks) → zoom terug naar volledig.
  useEffect(() => {
    setZoom(null)
    setDragStart(null)
    setDragEnd(null)
  }, [range])

  const maxIdx = Math.max(0, data.length - 1)
  const startIndex = zoom ? Math.min(zoom[0], maxIdx) : 0
  const endIndex = zoom ? Math.min(zoom[1], maxIdx) : maxIdx

  const last = data.length > 0 ? data[data.length - 1].price : null
  // Verandering over de getoonde periode; op 1D t.o.v. het vorige slot (zoals Yahoo).
  const base =
    range === '1d' && history?.prev_close !== null && history?.prev_close !== undefined
      ? Number(history.prev_close)
      : data.length > 0
        ? data[0].price
        : null
  const delta = last !== null && base !== null ? last - base : null
  const deltaPct = delta !== null && base !== null && base !== 0 ? (delta / base) * 100 : null
  const color = delta !== null && delta < 0 ? '#c62828' : '#008300'
  const currency = history?.currency ?? ''
  const prevClose = history?.prev_close != null ? Number(history.prev_close) : null

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-12 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl rounded-2xl border border-edge bg-surface p-5 shadow-lg max-md:max-h-[92dvh] max-md:overflow-y-auto max-md:rounded-b-none max-md:pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-medium">
            {name}
            <span className="ml-2 text-xs font-normal text-ink-3">{ticker}</span>
          </h3>
          <button onClick={onClose} className="text-sm text-ink-3 hover:text-ink-2">
            Sluiten
          </button>
        </div>

        {last !== null && (
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-2xl font-semibold tracking-tight tabular-nums">
              {priceFmt.format(last)}
              {currency && <span className="ml-1.5 text-sm font-normal text-ink-3">{currency}</span>}
            </span>
            {delta !== null && (
              <span
                className={`text-sm font-medium tabular-nums ${delta < 0 ? 'text-crit' : 'text-good'}`}
              >
                {delta > 0 ? '+' : ''}
                {priceFmt.format(delta)}
                {deltaPct !== null && (
                  <>
                    {' '}
                    ({deltaPct > 0 ? '+' : ''}
                    {pctFmt.format(deltaPct)} %)
                  </>
                )}
              </span>
            )}
            <span className="text-xs text-ink-3">
              {range === '1d' ? 't.o.v. vorig slot' : `over ${RANGES.find((r) => r.key === range)?.label}`}
            </span>
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-1">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              onClick={() => setRange(r.key)}
              aria-pressed={range === r.key}
              className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                range === r.key
                  ? 'bg-raised font-medium text-ink'
                  : 'text-ink-3 hover:bg-raised/60 hover:text-ink-2'
              }`}
            >
              {r.label}
            </button>
          ))}
          {loading && <span className="ml-2 self-center text-xs text-ink-3">Laden…</span>}
        </div>

        <div className="mt-3 h-80 touch-pan-y max-md:h-64">
          {error ? (
            <p className="flex h-full items-center justify-center text-sm text-crit">{error}</p>
          ) : data.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-1.5 px-6 text-center text-ink-3">
              {loading ? (
                <span className="text-sm">Laden…</span>
              ) : range === '1d' ? (
                <>
                  <span className="text-sm">Nog geen koersen voor vandaag.</span>
                  <span className="max-w-md text-xs">
                    De beurs is net open of Yahoo levert de (doorgaans ~15 min vertraagde)
                    intradaykoersen nog niet. Probeer straks opnieuw, of kies een langere periode.
                  </span>
                  {prevClose !== null && (
                    <span className="mt-1 text-xs">
                      Vorige slotkoers:{' '}
                      <span className="font-medium tabular-nums text-ink-2">
                        {priceFmt.format(prevClose)}
                        {currency ? ` ${currency}` : ''}
                      </span>
                    </span>
                  )}
                </>
              ) : (
                <span className="text-sm">Geen koersdata voor deze periode.</span>
              )}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={data}
                margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                {...pressHandlers}
                // Sleep-zoom is muiswerk; op touch zoomen de periodeknoppen en
                // moet slepen gewoon de pagina scrollen.
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
                    setZoom(dragStart < dragEnd ? [dragStart, dragEnd] : [dragEnd, dragStart])
                  }
                  setDragStart(null)
                  setDragEnd(null)
                }}
                onMouseLeave={() => {
                  setDragStart(null)
                  setDragEnd(null)
                }}
                onDoubleClick={() => {
                  setZoom(null)
                  setDragStart(null)
                  setDragEnd(null)
                }}
              >
                <defs>
                  <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.16} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#e1e0d9" />
                <XAxis
                  dataKey="i"
                  type="category"
                  ticks={ticks}
                  tickFormatter={(i: number) => data[i]?.label ?? ''}
                  tickLine={false}
                  axisLine={{ stroke: '#e1e0d9' }}
                  tick={{ fill: '#898781', fontSize: 11 }}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  tickLine={false}
                  axisLine={false}
                  width={56}
                  tick={{ fill: '#898781', fontSize: 11 }}
                  tickFormatter={(v: number) => priceFmt.format(v)}
                />
                <Tooltip
                  active={tooltipActive}
                  cursor={{ stroke: '#898781', strokeDasharray: '4 3' }}
                  formatter={(value) => [
                    `${priceFmt.format(value as number)}${currency ? ` ${currency}` : ''}`,
                    'Koers',
                  ]}
                  labelFormatter={(_, payload) => payload?.[0]?.payload?.tooltip ?? ''}
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid rgb(11 11 11 / 0.1)',
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                />
                {range === '1d' && prevClose !== null && (
                  <ReferenceLine y={prevClose} stroke="#898781" strokeDasharray="4 3" />
                )}
                <Area
                  type="linear"
                  dataKey="price"
                  stroke={color}
                  strokeWidth={2}
                  fill="url(#priceFill)"
                  dot={false}
                  isAnimationActive={false}
                />
                {/* Zone tijdens het slepen om een periode te selecteren. */}
                {dragStart !== null && dragEnd !== null && dragStart !== dragEnd && (
                  <ReferenceArea
                    x1={Math.min(dragStart, dragEnd)}
                    x2={Math.max(dragStart, dragEnd)}
                    fill="#898781"
                    fillOpacity={0.1}
                  />
                )}
                {/* Schuifbalk onderaan: sleep de handvatten of de balk om in te zoomen. */}
                <Brush
                  dataKey="i"
                  height={24}
                  travellerWidth={8}
                  gap={1}
                  stroke="#b8b7b0"
                  fill="rgba(11, 11, 11, 0.02)"
                  tickFormatter={(i: number) => data[i]?.label ?? ''}
                  startIndex={startIndex}
                  endIndex={endIndex}
                  onChange={(r) => {
                    if (
                      typeof r.startIndex === 'number' &&
                      typeof r.endIndex === 'number' &&
                      (r.startIndex !== 0 || r.endIndex !== maxIdx)
                    ) {
                      setZoom([r.startIndex, r.endIndex])
                    } else {
                      setZoom(null)
                    }
                  }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        <p className="mt-2 text-[11px] text-ink-3">
          Bron: Yahoo Finance, in de noteringsmunt van het effect
          {range === '1d' && prevClose !== null ? ' — stippellijn = vorig slot' : ''}.
        </p>
      </div>
    </div>
  )
}
