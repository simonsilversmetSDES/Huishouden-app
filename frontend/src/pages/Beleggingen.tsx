import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type {
  Benchmark,
  Portfolio,
  PortfolioHistory,
  PriceFetchResult,
  Security,
  SecurityKind,
  SecurityPayload,
  SecurityPricePayload,
  SecuritySearchHit,
  SecuritySide,
  SecuritySplit,
  SecuritySplitPayload,
  SecurityTransaction,
  SecurityTransactionPayload,
  YearReturn,
} from '../api/types'
import DonutCard from '../components/DonutCard'
import PortfolioHistoryChart from '../components/PortfolioHistoryChart'
import PriceChartModal from '../components/PriceChartModal'
import { formatCents, formatCentsPlain, formatDate } from '../lib/format'
import { useAppState } from '../state/AppState'

const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'

// Soort belegging → bepaalt de activaklasse in de vermogensbalans (spec §9).
const SECURITY_KINDS: { value: SecurityKind; label: string }[] = [
  { value: 'etf_fondsen', label: "Beleggingsfonds / ETF" },
  { value: 'aandelen', label: 'Aandeel' },
  { value: 'bitcoin', label: 'Bitcoin' },
]

const pctFmt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 2 })

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

/** Exacte Decimal-weergave: punt → komma (geen afronding). */
function dec(value: string | null): string {
  return value === null ? '–' : value.replace('.', ',')
}

const dec2Fmt = new Intl.NumberFormat('nl-BE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** Decimal-string op 2 decimalen (weergave voor gem. aankoop en koers). */
function dec2(value: string | null): string {
  return value === null ? '–' : dec2Fmt.format(Number(value))
}

/** nl-BE-invoer ("1.234,5" / "1234,5" / "1234.5") → Decimal-string met punt, of null. */
function normDec(input: string): string | null {
  const text = input.trim().replace(/\s/g, '').replace(/\./g, '').replace(',', '.')
  if (text === '' || !/^\d+(\.\d+)?$/.test(text)) return null
  return text
}

export default function Beleggingen() {
  const { contextId } = useAppState()
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [history, setHistory] = useState<PortfolioHistory | null>(null)
  const [securities, setSecurities] = useState<Security[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState<Security | null>(null)
  const [viewingTx, setViewingTx] = useState<{ id: number; name: string } | null>(null)
  const [chart, setChart] = useState<{ id: number; name: string; ticker: string } | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const knownRef = useRef<Set<number>>(new Set())
  const autoFetchedRef = useRef(false)

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    api<Portfolio>(`/api/portfolio?context_id=${contextId}`)
      .then(setPortfolio)
      .catch(() => setError('Portefeuille laden mislukt — probeer opnieuw'))
    api<Security[]>(`/api/securities?context_id=${contextId}`)
      .then(setSecurities)
      .catch(() => setSecurities([]))
    api<PortfolioHistory>(`/api/portfolio/history?context_id=${contextId}`)
      .then(setHistory)
      .catch(() => setHistory(null))
  }, [contextId])

  useEffect(load, [load])

  // Nieuwe effecten staan standaard aangevinkt; bestaande selectie blijft behouden.
  useEffect(() => {
    if (!portfolio) return
    const fresh = portfolio.positions
      .map((p) => p.security_id)
      .filter((id) => !knownRef.current.has(id))
    if (fresh.length === 0) return
    fresh.forEach((id) => knownRef.current.add(id))
    setSelected((prev) => new Set([...prev, ...fresh]))
  }, [portfolio])

  // Koersen verversen bij het openen van de tab (één keer per context).
  useEffect(() => {
    if (contextId === null || autoFetchedRef.current) return
    autoFetchedRef.current = true
    api<PriceFetchResult>(`/api/prices/fetch?context_id=${contextId}`, { method: 'POST' })
      .then((res) => {
        if (res.fetched > 0) load()
      })
      .catch(() => {
        /* stil: koersen uitgeschakeld of netwerkfout */
      })
  }, [contextId, load])

  if (contextId === null) return null

  async function fetchPrices() {
    setNotice(null)
    try {
      const res = await api<PriceFetchResult>(`/api/prices/fetch?context_id=${contextId}`, {
        method: 'POST',
      })
      const failed = res.failed.length > 0 ? ` (mislukt: ${res.failed.join(', ')})` : ''
      setNotice(`${res.fetched} koers(en) opgehaald${failed}.`)
      load()
    } catch (err) {
      setNotice(
        err instanceof ApiError && err.status === 503
          ? 'Koersen ophalen is uitgeschakeld (price_fetch_enabled).'
          : 'Koersen ophalen mislukt — probeer opnieuw.',
      )
    }
  }

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Overzicht/totalen/donut enkel op de aangevinkte effecten.
  const visible = portfolio ? portfolio.positions.filter((p) => selected.has(p.security_id)) : []
  const totalValue = visible.reduce((sum, p) => sum + (p.value_cents ?? 0), 0)
  const totalCost = visible.reduce((sum, p) => sum + p.cost_cents, 0)
  const totalGain = totalValue - totalCost
  const totalGainPct = totalCost > 0 ? (totalGain / totalCost) * 100 : null
  const donutRows = visible
    .filter((p) => p.value_cents !== null && p.value_cents > 0)
    .map((p) => ({ name: p.name, cents: p.value_cents as number }))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Beleggingen</h1>
        <button
          onClick={() => void fetchPrices()}
          className="ml-auto rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 transition-colors hover:bg-raised"
        >
          Koersen ophalen
        </button>
      </div>
      {notice && <p className="text-sm text-ink-3">{notice}</p>}

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {!error && portfolio && (
        <>
          <Overview
            totalValueCents={totalValue}
            totalCostCents={totalCost}
            gainCents={totalGain}
            gainPct={totalGainPct}
            donutRows={donutRows}
          />
          <PortfolioHistoryChart history={history} selected={selected} />
          <YearlyReturns years={portfolio.yearly_returns} benchmark={portfolio.benchmark} />
          <PositionsTable
            portfolio={portfolio}
            securities={securities}
            selected={selected}
            selectedTotalValue={totalValue}
            onToggle={toggle}
            onEdit={setEditing}
            onViewTransactions={(id, name) => setViewingTx({ id, name })}
            onShowChart={(id, name, ticker) => setChart({ id, name, ticker })}
          />
          <RealizedGains portfolio={portfolio} />
          <EntrySection
            contextId={contextId}
            securities={securities}
            onChanged={load}
          />
        </>
      )}

      {editing && (
        <EditSecurityModal
          security={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}

      {chart && (
        <PriceChartModal
          securityId={chart.id}
          name={chart.name}
          ticker={chart.ticker}
          onClose={() => setChart(null)}
        />
      )}

      {viewingTx && (
        <TransactionsModal
          securityId={viewingTx.id}
          name={viewingTx.name}
          onClose={() => setViewingTx(null)}
          onChanged={load}
        />
      )}
    </div>
  )
}

function Overview({
  totalValueCents,
  totalCostCents,
  gainCents,
  gainPct,
  donutRows,
}: {
  totalValueCents: number
  totalCostCents: number
  gainCents: number
  gainPct: number | null
  donutRows: { name: string; cents: number }[]
}) {
  return (
    <section className="grid gap-4 lg:grid-cols-2">
      <div className="grid gap-4 sm:grid-cols-3 lg:col-span-1 lg:grid-cols-1">
        <Tile label="Totale waarde" value={formatCents(totalValueCents)} />
        <Tile label="Totale inleg" value={formatCents(totalCostCents)} />
        <Tile
          label="Rendement"
          value={`${gainCents > 0 ? '+' : ''}${formatCents(gainCents)}`}
          tone={gainCents < 0 ? 'crit' : 'good'}
          extra={
            gainPct !== null ? `${gainCents > 0 ? '+' : ''}${pctFmt.format(gainPct)} %` : undefined
          }
        />
      </div>
      <DonutCard title="Verdeling portefeuille" kind="saving" rows={donutRows} />
    </section>
  )
}

function YearPct({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-ink-3">onvolledig</span>
  return (
    <span className={pct < 0 ? 'text-crit' : 'text-good'}>
      {pct > 0 ? '+' : ''}
      {pctFmt.format(pct)} %
    </span>
  )
}

function YearlyReturns({ years, benchmark }: { years: YearReturn[]; benchmark: Benchmark | null }) {
  if (years.length === 0) return null
  const anyComplete = years.some((y) => y.return_pct !== null)
  const benchByYear = new Map((benchmark?.years ?? []).map((y) => [y.year, y]))
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h2 className="text-base font-medium">Rendement per jaar</h2>
        <span className="text-xs text-ink-3">
          per kalenderjaar, rekening houdend met stortingen (Modified Dietz)
        </span>
      </div>
      {!anyComplete ? (
        <p className="rounded-2xl border border-dashed border-edge bg-surface px-4 py-3 text-sm text-ink-2">
          Nog geen historische koersen beschikbaar. Het rendement per jaar verschijnt
          zodra er per jaargrens (eind december) een koers gekend is — die bouwt vanzelf
          op naarmate de koersen dagelijks worden bijgehouden.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {years.map((y) => {
              const bench = benchByYear.get(y.year)
              return (
                <div
                  key={y.year}
                  className="rounded-2xl border border-edge bg-surface px-4 py-3 text-sm"
                  title={
                    y.complete
                      ? undefined
                      : 'Onvoldoende historische koersen om dit jaar te waarderen'
                  }
                >
                  <span className="text-ink-3">{y.year}: </span>
                  <span className="font-medium">
                    <YearPct pct={y.return_pct} />
                  </span>
                  <div className="mt-1 space-y-0.5 text-xs text-ink-3">
                    <div>
                      {y.net_flow_cents >= 0 ? 'gestort: ' : 'afgenomen: '}
                      <span className="text-ink-2">
                        {formatCents(Math.abs(y.net_flow_cents))}
                      </span>
                    </div>
                    <div>
                      {y.year === new Date().getFullYear() ? 'waarde nu: ' : 'eindwaarde: '}
                      <span className="text-ink-2">{formatCents(y.end_value_cents)}</span>
                    </div>
                  </div>
                  {bench && (
                    <div className="mt-1 border-t border-line pt-1 text-xs text-ink-3">
                      referentie: <YearPct pct={bench.return_pct} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {benchmark && (
            <p className="text-xs text-ink-3">
              "referentie" = koersrendement van {benchmark.name} (geen Modified Dietz — dus
              onafhankelijk van wanneer jij instapte of bijstortte).
            </p>
          )}
        </>
      )}
    </section>
  )
}

function Tile({
  label,
  value,
  tone,
  extra,
}: {
  label: string
  value: string
  tone?: 'good' | 'crit'
  extra?: string
}) {
  return (
    <div className="rounded-2xl border border-edge bg-surface p-5">
      <p className="text-sm text-ink-3">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold tracking-tight ${
          tone === 'crit' ? 'text-crit' : tone === 'good' ? 'text-good' : ''
        }`}
      >
        {value}
      </p>
      {extra && <p className="mt-2 text-xs text-ink-3">{extra}</p>}
    </div>
  )
}

/** Winst-cel: bedrag met percentage eronder — vermijdt omslaande regels. */
function GainCell({ cents, pct }: { cents: number | null; pct: number | null }) {
  if (cents === null) return <span className="text-ink-3">–</span>
  const tone = cents < 0 ? 'text-crit' : cents > 0 ? 'text-good' : 'text-ink-3'
  return (
    <div className="leading-tight">
      <div className={tone}>
        {cents > 0 ? '+' : ''}
        {formatCentsPlain(cents)}
      </div>
      {pct !== null && (
        <div className="text-xs text-ink-3">
          {pct > 0 ? '+' : ''}
          {pctFmt.format(pct)} %
        </div>
      )}
    </div>
  )
}

function PositionsTable({
  portfolio,
  securities,
  selected,
  selectedTotalValue,
  onToggle,
  onEdit,
  onViewTransactions,
  onShowChart,
}: {
  portfolio: Portfolio
  securities: Security[]
  selected: Set<number>
  selectedTotalValue: number
  onToggle: (securityId: number) => void
  onEdit: (security: Security) => void
  onViewTransactions: (securityId: number, name: string) => void
  onShowChart: (securityId: number, name: string, ticker: string) => void
}) {
  if (portfolio.positions.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center text-sm text-ink-2">
        Nog geen effecten. Voeg er hieronder een toe en log transacties.
      </div>
    )
  }
  const byId = new Map(securities.map((s) => [s.id, s]))
  // Grootste positie bovenaan; effecten zonder waarde onderaan.
  const rows = [...portfolio.positions].sort(
    (a, b) => (b.value_cents ?? -1) - (a.value_cents ?? -1),
  )
  const visible = rows.filter((p) => selected.has(p.security_id))
  const dayCells = visible.map((p) => p.day_gain_cents).filter((c): c is number => c !== null)
  const totalDay = dayCells.length > 0 ? dayCells.reduce((sum, c) => sum + c, 0) : null
  const totalCost = visible.reduce((sum, p) => sum + p.cost_cents, 0)
  const totalGain = selectedTotalValue - totalCost
  const th = 'px-3 py-3 text-right text-xs font-medium uppercase tracking-wide'
  return (
    <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[980px] text-sm">
        <thead>
          <tr className="border-b border-line text-ink-3">
            <th className="py-3 pl-5 pr-1" />
            <th className={`${th} text-left`}>Effect</th>
            <th className={th}>Aantal</th>
            <th className={th}>Koers</th>
            <th className={th}>Waarde</th>
            <th className={th}>Vandaag</th>
            <th className={th}>Winst/verlies</th>
            <th className={th}>% port.</th>
            <th className="px-5 py-3" />
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((p) => {
            const on = selected.has(p.security_id)
            const pct =
              on && p.value_cents !== null && selectedTotalValue > 0
                ? (p.value_cents / selectedTotalValue) * 100
                : null
            return (
              <tr
                key={p.security_id}
                className={`border-b border-line transition-opacity last:border-b-0 hover:bg-raised/50 ${
                  on ? '' : 'opacity-40'
                }`}
              >
                <td className="py-2.5 pl-5 pr-1">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => onToggle(p.security_id)}
                    aria-label={`${p.name} meetellen`}
                    className="size-4 accent-accent"
                  />
                </td>
                <td className="px-3 py-2.5">
                  {p.ticker ? (
                    <button
                      onClick={() => onShowChart(p.security_id, p.name, p.ticker as string)}
                      title="Koersgrafiek tonen"
                      className="group block text-left leading-tight"
                    >
                      <span className="font-medium group-hover:text-accent group-hover:underline">
                        {p.name}
                      </span>
                      <span className="mt-0.5 block font-mono text-[11px] tracking-wide text-ink-3">
                        {p.ticker}
                      </span>
                    </button>
                  ) : (
                    <div className="leading-tight">
                      <span className="font-medium">{p.name}</span>
                      <span className="mt-0.5 block text-[11px] text-warn">geen ticker</span>
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-right text-ink-2">{dec(p.shares)}</td>
                <td className="px-3 py-2.5 text-right text-ink-2">{dec2(p.current_price)}</td>
                <td className="px-3 py-2.5 text-right font-medium">
                  {p.value_cents === null ? (
                    <span className="font-normal text-ink-3">–</span>
                  ) : (
                    formatCentsPlain(p.value_cents)
                  )}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <GainCell cents={p.day_gain_cents} pct={p.day_gain_pct} />
                </td>
                <td className="px-3 py-2.5 text-right">
                  <GainCell cents={p.gain_cents} pct={p.gain_pct} />
                </td>
                <td className="px-3 py-2.5 text-right text-ink-2">
                  {pct !== null ? (
                    <div className="flex items-center justify-end gap-2">
                      <span>{pctFmt.format(pct)} %</span>
                      <span className="h-1.5 w-12 shrink-0 overflow-hidden rounded-full bg-raised">
                        <span
                          className="block h-full rounded-full bg-saving/70"
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </span>
                    </div>
                  ) : (
                    <span className="text-ink-3">–</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-5 py-2.5 text-right">
                  <button
                    onClick={() => onViewTransactions(p.security_id, p.name)}
                    className="text-xs text-ink-3 hover:text-ink-2 hover:underline"
                  >
                    Transacties
                  </button>
                  {byId.has(p.security_id) && (
                    <button
                      onClick={() => onEdit(byId.get(p.security_id) as Security)}
                      className="ml-3 text-xs text-ink-3 hover:text-ink-2 hover:underline"
                    >
                      Bewerken
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
        <tfoot className="tabular-nums">
          <tr className="border-t-2 border-line bg-raised/40 font-medium">
            <td className="py-2.5 pl-5 pr-1" />
            <td className="px-3 py-2.5">Totaal</td>
            <td />
            <td />
            <td className="px-3 py-2.5 text-right">{formatCentsPlain(selectedTotalValue)}</td>
            <td className="px-3 py-2.5 text-right">
              <GainCell cents={totalDay} pct={null} />
            </td>
            <td className="px-3 py-2.5 text-right">
              <GainCell
                cents={totalGain}
                pct={totalCost > 0 ? (totalGain / totalCost) * 100 : null}
              />
            </td>
            <td />
            <td className="px-5 py-2.5" />
          </tr>
        </tfoot>
      </table>
    </section>
  )
}

function EditSecurityModal({
  security,
  onClose,
  onSaved,
}: {
  security: Security
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(security.name)
  const [ticker, setTicker] = useState(security.ticker ?? '')
  const [isin, setIsin] = useState(security.isin ?? '')
  const [soort, setSoort] = useState<SecurityKind>(security.soort)
  const [isBenchmark, setIsBenchmark] = useState(security.is_benchmark)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SecuritySearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Debounced Yahoo-zoekopdracht.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      return
    }
    setSearching(true)
    const timer = setTimeout(() => {
      api<SecuritySearchHit[]>(`/api/securities/search?q=${encodeURIComponent(q)}`)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  async function save() {
    setError(null)
    setBusy(true)
    const payload: SecurityPayload = {
      name: name.trim(),
      ticker: ticker.trim() || null,
      isin: isin.trim() || null,
      owner_context_id: security.owner_context_id,
      soort,
      is_benchmark: isBenchmark,
    }
    try {
      await api(`/api/securities/${security.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm(`Effect "${security.name}" en al zijn transacties verwijderen?`)) return
    setBusy(true)
    try {
      await api(`/api/securities/${security.id}`, { method: 'DELETE' })
      onSaved()
    } catch {
      setError('Verwijderen mislukt')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-16"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-edge bg-surface p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-medium">Effect bewerken</h3>
        <div className="mt-3 space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Naam</span>
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Soort</span>
            <select
              className={inputClass}
              value={soort}
              onChange={(e) => setSoort(e.target.value as SecurityKind)}
            >
              {SECURITY_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-sm text-ink-2">
            <input
              type="checkbox"
              checked={isBenchmark}
              onChange={(e) => setIsBenchmark(e.target.checked)}
              className="size-4 accent-accent"
            />
            Gebruik als referentie-index (wereldindex) op de Vermogen-tab
          </label>
          {isBenchmark && (
            <p className="text-xs text-ink-3">
              Er kan maar één referentie-index per persoon zijn — een ander gemarkeerd
              effect wordt automatisch uitgevinkt.
            </p>
          )}

          <label className="block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
              Ticker (yfinance)
            </span>
            <input
              className={inputClass}
              value={ticker}
              placeholder="bv. IWDA.AS"
              onChange={(e) => setTicker(e.target.value)}
            />
          </label>
          {security.suggested_ticker && security.suggested_ticker !== ticker && (
            <button
              type="button"
              onClick={() => setTicker(security.suggested_ticker as string)}
              className="rounded-lg bg-raised px-2.5 py-1 text-xs text-ink-2 hover:bg-raised/70"
            >
              Gebruik suggestie: {security.suggested_ticker}
            </button>
          )}

          <label className="block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
              Zoeken op Yahoo Finance
            </span>
            <input
              className={inputClass}
              value={query}
              placeholder="bv. alphabet"
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {searching && <p className="text-xs text-ink-3">Zoeken…</p>}
          {results.length > 0 && (
            <ul className="max-h-48 overflow-y-auto rounded-lg border border-edge">
              {results.map((hit) => (
                <li key={hit.symbol}>
                  <button
                    type="button"
                    onClick={() => {
                      setTicker(hit.symbol)
                      setResults([])
                      setQuery('')
                    }}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-raised"
                  >
                    <span className="font-medium">{hit.symbol}</span>
                    <span className="truncate text-ink-2">{hit.name}</span>
                    <span className="ml-auto shrink-0 text-xs text-ink-3">{hit.exchange}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <label className="block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">ISIN</span>
            <input className={inputClass} value={isin} onChange={(e) => setIsin(e.target.value)} />
          </label>
        </div>

        {error && <p className="mt-2 text-sm text-crit">{error}</p>}

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => void save()}
            disabled={busy}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
          >
            Opslaan
          </button>
          <button
            onClick={onClose}
            className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 hover:bg-raised"
          >
            Annuleren
          </button>
          <button
            onClick={() => void remove()}
            disabled={busy}
            className="ml-auto text-sm text-ink-3 hover:text-crit hover:underline"
          >
            Effect verwijderen
          </button>
        </div>
      </div>
    </div>
  )
}

interface TxDraft {
  date: string
  side: SecuritySide
  shares: string
  price: string
  fee: string
  tax: string
}

function SplitsBlock({
  securityId,
  onChanged,
}: {
  securityId: number
  onChanged: () => void
}) {
  const [splits, setSplits] = useState<SecuritySplit[] | null>(null)
  const [date, setDate] = useState(todayIso)
  const [ratio, setRatio] = useState('')
  const [alsoOthers, setAlsoOthers] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    api<SecuritySplit[]>(`/api/security-splits?security_id=${securityId}`)
      .then(setSplits)
      .catch(() => setSplits([]))
  }, [securityId])

  useEffect(reload, [reload])

  async function add(e: FormEvent) {
    e.preventDefault()
    const r = normDec(ratio)
    if (r === null) {
      setError('Ongeldige ratio')
      return
    }
    setError(null)
    const payload: SecuritySplitPayload = {
      security_id: securityId,
      date,
      ratio: r,
      apply_to_other_contexts: alsoOthers,
    }
    try {
      await api('/api/security-splits', { method: 'POST', body: JSON.stringify(payload) })
      setRatio('')
      reload()
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Split opslaan mislukt')
    }
  }

  async function remove(s: SecuritySplit) {
    if (!window.confirm(`Split van ${formatDate(s.date)} (${dec(s.ratio)}:1) verwijderen?`)) return
    await api(`/api/security-splits/${s.id}`, { method: 'DELETE' })
    reload()
    onChanged()
  }

  return (
    <div className="mt-3 rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-3">
          Aandelensplitsingen
        </span>
        {splits?.map((s) => (
          <span key={s.id} className="flex items-center gap-1 text-xs text-ink-2">
            {formatDate(s.date)}: {dec(s.ratio)}:1
            <button
              onClick={() => void remove(s)}
              aria-label="Split verwijderen"
              className="text-ink-3 hover:text-crit"
            >
              ×
            </button>
          </span>
        ))}
        {splits?.length === 0 && <span className="text-xs text-ink-3">geen</span>}
      </div>
      <form onSubmit={add} className="mt-2 flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded border border-edge bg-page px-2 py-1 text-sm"
        />
        <input
          value={ratio}
          placeholder="ratio (bv. 25)"
          onChange={(e) => setRatio(e.target.value)}
          className="w-28 rounded border border-edge bg-page px-2 py-1 text-sm text-right"
        />
        <button
          type="submit"
          className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent/85"
        >
          Split toevoegen
        </button>
        <label className="flex items-center gap-1.5 text-xs text-ink-2">
          <input
            type="checkbox"
            checked={alsoOthers}
            onChange={(e) => setAlsoOthers(e.target.checked)}
            className="size-3.5 accent-accent"
          />
          ook op andere portefeuilles
        </label>
        {error && <span className="text-xs text-crit">{error}</span>}
      </form>
      <p className="mt-1 text-[11px] text-ink-3">
        Bij een 25:1-split: transacties vóór de datum krijgen aantal × 25 en prijs ÷ 25.
      </p>
    </div>
  )
}

function TransactionsModal({
  securityId,
  name,
  onClose,
  onChanged,
}: {
  securityId: number
  name: string
  onClose: () => void
  onChanged: () => void
}) {
  const [rows, setRows] = useState<SecurityTransaction[] | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState<TxDraft | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    api<SecurityTransaction[]>(`/api/security-transactions?security_id=${securityId}`)
      .then(setRows)
      .catch(() => setError('Transacties laden mislukt'))
  }, [securityId])

  useEffect(reload, [reload])

  function startEdit(tx: SecurityTransaction) {
    setEditingId(tx.id)
    setDraft({
      date: tx.date,
      side: tx.side,
      shares: dec(tx.shares),
      price: dec(tx.price_per_share),
      fee: dec(tx.fee),
      tax: dec(tx.tax),
    })
  }

  async function saveEdit(id: number) {
    if (draft === null) return
    const shares = normDec(draft.shares)
    const price = normDec(draft.price)
    if (shares === null || price === null) {
      setError('Aantal en prijs zijn verplicht')
      return
    }
    setError(null)
    const payload: SecurityTransactionPayload = {
      security_id: securityId,
      date: draft.date,
      side: draft.side,
      shares,
      price_per_share: price,
      fee: normDec(draft.fee) ?? '0',
      tax: normDec(draft.tax) ?? '0',
    }
    try {
      await api(`/api/security-transactions/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      setEditingId(null)
      setDraft(null)
      reload()
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt')
    }
  }

  async function remove(tx: SecurityTransaction) {
    if (!window.confirm(`Transactie van ${formatDate(tx.date)} verwijderen?`)) return
    try {
      await api(`/api/security-transactions/${tx.id}`, { method: 'DELETE' })
      reload()
      onChanged()
    } catch {
      setError('Verwijderen mislukt')
    }
  }

  const cell = 'w-full rounded border border-accent bg-page px-1.5 py-1 text-sm'

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-12"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl rounded-2xl border border-edge bg-surface p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-medium">Transacties — {name}</h3>
          <button onClick={onClose} className="text-sm text-ink-3 hover:text-ink-2">
            Sluiten
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-crit">{error}</p>}

        <SplitsBlock securityId={securityId} onChanged={onChanged} />

        <div className="mt-3 overflow-x-auto">
          {rows === null ? (
            <p className="py-8 text-center text-sm text-ink-3">Laden…</p>
          ) : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-ink-2">Geen transacties.</p>
          ) : (
            <table className="w-full min-w-[640px] text-sm tabular-nums">
              <thead>
                <tr className="border-b border-line text-xs text-ink-3">
                  <th className="px-2 py-2 text-left font-medium">Datum</th>
                  <th className="px-2 py-2 text-left font-medium">Type</th>
                  <th className="px-2 py-2 text-right font-medium">Aantal</th>
                  <th className="px-2 py-2 text-right font-medium">Prijs</th>
                  <th className="px-2 py-2 text-right font-medium">Kost</th>
                  <th className="px-2 py-2 text-right font-medium">TOB</th>
                  <th className="px-2 py-2 text-right font-medium">Totaal</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((tx) =>
                  editingId === tx.id && draft ? (
                    <tr key={tx.id} className="border-b border-line">
                      <td className="px-1 py-1">
                        <input
                          type="date"
                          className={cell}
                          value={draft.date}
                          onChange={(e) => setDraft({ ...draft, date: e.target.value })}
                        />
                      </td>
                      <td className="px-1 py-1">
                        <select
                          className={cell}
                          value={draft.side}
                          onChange={(e) =>
                            setDraft({ ...draft, side: e.target.value as SecuritySide })
                          }
                        >
                          <option value="buy">Aankoop</option>
                          <option value="sell">Verkoop</option>
                        </select>
                      </td>
                      {(['shares', 'price', 'fee', 'tax'] as const).map((field) => (
                        <td key={field} className="px-1 py-1">
                          <input
                            className={`${cell} text-right`}
                            value={draft[field]}
                            onChange={(e) => setDraft({ ...draft, [field]: e.target.value })}
                          />
                        </td>
                      ))}
                      <td className="px-2 py-1 text-right text-ink-3">–</td>
                      <td className="whitespace-nowrap px-2 py-1 text-right">
                        <button
                          onClick={() => void saveEdit(tx.id)}
                          className="text-xs text-accent hover:underline"
                        >
                          Opslaan
                        </button>
                        <button
                          onClick={() => {
                            setEditingId(null)
                            setDraft(null)
                          }}
                          className="ml-2 text-xs text-ink-3 hover:text-ink-2"
                        >
                          Annuleren
                        </button>
                      </td>
                    </tr>
                  ) : (
                    <tr key={tx.id} className="border-b border-line last:border-b-0 hover:bg-raised/50">
                      <td className="whitespace-nowrap px-2 py-1.5">{formatDate(tx.date)}</td>
                      <td className="px-2 py-1.5">{tx.side === 'buy' ? 'Aankoop' : 'Verkoop'}</td>
                      <td className="px-2 py-1.5 text-right">{dec(tx.shares)}</td>
                      <td className="px-2 py-1.5 text-right text-ink-2">{dec(tx.price_per_share)}</td>
                      <td className="px-2 py-1.5 text-right text-ink-2">{dec(tx.fee)}</td>
                      <td className="px-2 py-1.5 text-right text-ink-2">{dec(tx.tax)}</td>
                      <td className="px-2 py-1.5 text-right">{dec(tx.total)}</td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right">
                        <button
                          onClick={() => startEdit(tx)}
                          className="text-xs text-ink-3 hover:text-ink-2 hover:underline"
                        >
                          Bewerken
                        </button>
                        <button
                          onClick={() => void remove(tx)}
                          className="ml-2 text-xs text-ink-3 hover:text-crit hover:underline"
                        >
                          Verwijderen
                        </button>
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function RealizedGains({ portfolio }: { portfolio: Portfolio }) {
  if (portfolio.realized_gains.length === 0) return null
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h2 className="text-base font-medium">Gerealiseerde meerwaarden</h2>
        <span className="text-xs text-ink-3">
          berekening o.b.v. gemiddelde aankoopprijs — geen fiscaal advies
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {portfolio.realized_by_year.map((y) => (
          <div key={y.year} className="rounded-2xl border border-edge bg-surface px-4 py-3 text-sm">
            <span className="text-ink-3">{y.year}: </span>
            <span className={`font-medium ${y.gain_cents < 0 ? 'text-crit' : 'text-good'}`}>
              {y.gain_cents > 0 ? '+' : ''}
              {formatCents(y.gain_cents)}
            </span>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-edge bg-surface">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-ink-3">
              <th className="px-5 py-3 text-left font-medium">Datum</th>
              <th className="px-3 py-3 text-left font-medium">Effect</th>
              <th className="px-3 py-3 text-right font-medium">Aantal</th>
              <th className="px-3 py-3 text-right font-medium">Opbrengst</th>
              <th className="px-3 py-3 text-right font-medium">Kostbasis</th>
              <th className="px-5 py-3 text-right font-medium">Meerwaarde</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {portfolio.realized_gains.map((g, i) => (
              <tr
                key={`${g.security_id}-${g.date}-${i}`}
                className="border-b border-line last:border-b-0"
              >
                <td className="whitespace-nowrap px-5 py-2">{formatDate(g.date)}</td>
                <td className="px-3 py-2">{g.name}</td>
                <td className="px-3 py-2 text-right text-ink-2">{dec(g.shares)}</td>
                <td className="px-3 py-2 text-right text-ink-2">
                  {formatCentsPlain(g.proceeds_cents)}
                </td>
                <td className="px-3 py-2 text-right text-ink-2">
                  {formatCentsPlain(g.cost_basis_cents)}
                </td>
                <td className="px-5 py-2 text-right">
                  <span className={g.gain_cents < 0 ? 'text-crit' : 'text-good'}>
                    {g.gain_cents > 0 ? '+' : ''}
                    {formatCentsPlain(g.gain_cents)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function EntrySection({
  contextId,
  securities,
  onChanged,
}: {
  contextId: number
  securities: Security[]
  onChanged: () => void
}) {
  return (
    <details className="rounded-2xl border border-edge bg-surface">
      <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-ink-2">
        Effect toevoegen / transactie loggen / koers invoeren
      </summary>
      <section className="grid gap-4 border-t border-line p-5 lg:grid-cols-3">
        <SecurityForm contextId={contextId} onSaved={onChanged} />
        <TransactionForm securities={securities} onSaved={onChanged} />
        <PriceForm securities={securities} onSaved={onChanged} />
      </section>
    </details>
  )
}

function SecurityForm({ contextId, onSaved }: { contextId: number; onSaved: () => void }) {
  const [name, setName] = useState('')
  const [ticker, setTicker] = useState('')
  const [isin, setIsin] = useState('')
  const [soort, setSoort] = useState<SecurityKind>('etf_fondsen')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (name.trim() === '') {
      setError('Naam is verplicht')
      return
    }
    setError(null)
    const payload: SecurityPayload = {
      name: name.trim(),
      ticker: ticker.trim() || null,
      isin: isin.trim() || null,
      owner_context_id: contextId,
      soort,
      is_benchmark: false,
    }
    try {
      await api<Security>('/api/securities', { method: 'POST', body: JSON.stringify(payload) })
      setName('')
      setTicker('')
      setIsin('')
      setSoort('etf_fondsen')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt')
    }
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium">Effect toevoegen</h3>
      <div className="mt-3 space-y-2">
        <input
          className={inputClass}
          placeholder="Naam (bv. iShares IWDA)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select
          className={inputClass}
          value={soort}
          onChange={(e) => setSoort(e.target.value as SecurityKind)}
        >
          {SECURITY_KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
        <input
          className={inputClass}
          placeholder="Ticker (bv. IWDA.AS) — optioneel"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
        />
        <input
          className={inputClass}
          placeholder="ISIN — optioneel"
          value={isin}
          onChange={(e) => setIsin(e.target.value)}
        />
      </div>
      <button
        type="submit"
        className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85"
      >
        Toevoegen
      </button>
      {error && <p className="mt-2 text-sm text-crit">{error}</p>}
    </form>
  )
}

function TransactionForm({
  securities,
  onSaved,
}: {
  securities: Security[]
  onSaved: () => void
}) {
  const [securityId, setSecurityId] = useState<number | ''>('')
  const [date, setDate] = useState(todayIso)
  const [side, setSide] = useState<SecuritySide>('buy')
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [fee, setFee] = useState('')
  const [tax, setTax] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const s = normDec(shares)
    const p = normDec(price)
    if (securityId === '' || s === null || p === null) {
      setError('Effect, aantal en prijs zijn verplicht')
      return
    }
    setError(null)
    const payload: SecurityTransactionPayload = {
      security_id: securityId,
      date,
      side,
      shares: s,
      price_per_share: p,
      fee: normDec(fee) ?? '0',
      tax: normDec(tax) ?? '0',
    }
    try {
      await api('/api/security-transactions', { method: 'POST', body: JSON.stringify(payload) })
      setShares('')
      setPrice('')
      setFee('')
      setTax('')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt')
    }
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium">Transactie loggen</h3>
      <div className="mt-3 space-y-2">
        <select
          className={inputClass}
          value={securityId}
          onChange={(e) => setSecurityId(e.target.value === '' ? '' : Number(e.target.value))}
        >
          <option value="">— kies effect —</option>
          {securities.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-2">
          <input type="date" className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
          <select className={inputClass} value={side} onChange={(e) => setSide(e.target.value as SecuritySide)}>
            <option value="buy">Aankoop</option>
            <option value="sell">Verkoop</option>
          </select>
          <input
            className={`${inputClass} text-right`}
            placeholder="Aantal"
            value={shares}
            onChange={(e) => setShares(e.target.value)}
          />
          <input
            className={`${inputClass} text-right`}
            placeholder="Prijs/stuk"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
          <input
            className={`${inputClass} text-right`}
            placeholder="Kost"
            value={fee}
            onChange={(e) => setFee(e.target.value)}
          />
          <input
            className={`${inputClass} text-right`}
            placeholder="Beurstaks (TOB)"
            value={tax}
            onChange={(e) => setTax(e.target.value)}
          />
        </div>
      </div>
      <button
        type="submit"
        className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85"
      >
        Loggen
      </button>
      {error && <p className="mt-2 text-sm text-crit">{error}</p>}
    </form>
  )
}

function PriceForm({ securities, onSaved }: { securities: Security[]; onSaved: () => void }) {
  const [securityId, setSecurityId] = useState<number | ''>('')
  const [date, setDate] = useState(todayIso)
  const [price, setPrice] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const p = normDec(price)
    if (securityId === '' || p === null) {
      setError('Effect en koers zijn verplicht')
      return
    }
    setError(null)
    const payload: SecurityPricePayload = { security_id: securityId, date, price: p }
    try {
      await api('/api/security-prices', { method: 'PUT', body: JSON.stringify(payload) })
      setPrice('')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt')
    }
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium">Koers invoeren (manueel)</h3>
      <div className="mt-3 space-y-2">
        <select
          className={inputClass}
          value={securityId}
          onChange={(e) => setSecurityId(e.target.value === '' ? '' : Number(e.target.value))}
        >
          <option value="">— kies effect —</option>
          {securities.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-2">
          <input type="date" className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
          <input
            className={`${inputClass} text-right`}
            placeholder="Koers"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
        </div>
      </div>
      <button
        type="submit"
        className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85"
      >
        Opslaan
      </button>
      <p className="mt-2 text-xs text-ink-3">
        Voor fondsen zonder ticker en de groepsverzekering.
      </p>
      {error && <p className="mt-2 text-sm text-crit">{error}</p>}
    </form>
  )
}
