import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type {
  Portfolio,
  PriceFetchResult,
  Security,
  SecurityPayload,
  SecurityPricePayload,
  SecuritySearchHit,
  SecuritySide,
  SecurityTransaction,
  SecurityTransactionPayload,
} from '../api/types'
import DonutCard from '../components/DonutCard'
import { formatCents, formatCentsPlain, formatDate } from '../lib/format'
import { useAppState } from '../state/AppState'

const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'

const pctFmt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 2 })

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

/** Exacte Decimal-weergave: punt → komma (geen afronding). */
function dec(value: string | null): string {
  return value === null ? '–' : value.replace('.', ',')
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
  const [securities, setSecurities] = useState<Security[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState<Security | null>(null)
  const [viewingTx, setViewingTx] = useState<{ id: number; name: string } | null>(null)

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    api<Portfolio>(`/api/portfolio?context_id=${contextId}`)
      .then(setPortfolio)
      .catch(() => setError('Portefeuille laden mislukt — probeer opnieuw'))
    api<Security[]>(`/api/securities?context_id=${contextId}`)
      .then(setSecurities)
      .catch(() => setSecurities([]))
  }, [contextId])

  useEffect(load, [load])

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
          <Overview portfolio={portfolio} />
          <PositionsTable
            portfolio={portfolio}
            securities={securities}
            onEdit={setEditing}
            onViewTransactions={(id, name) => setViewingTx({ id, name })}
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

function Overview({ portfolio }: { portfolio: Portfolio }) {
  const gain = portfolio.total_gain_cents
  const donutRows = portfolio.positions
    .filter((p) => p.value_cents !== null && p.value_cents > 0)
    .map((p) => ({ name: p.name, cents: p.value_cents as number }))

  return (
    <section className="grid gap-4 lg:grid-cols-2">
      <div className="grid gap-4 sm:grid-cols-3 lg:col-span-1 lg:grid-cols-1">
        <Tile label="Totale waarde" value={formatCents(portfolio.total_value_cents)} />
        <Tile label="Totale inleg" value={formatCents(portfolio.total_cost_cents)} />
        <Tile
          label="Rendement"
          value={`${gain > 0 ? '+' : ''}${formatCents(gain)}`}
          tone={gain < 0 ? 'crit' : 'good'}
          extra={
            portfolio.total_gain_pct !== null
              ? `${gain > 0 ? '+' : ''}${pctFmt.format(portfolio.total_gain_pct)} %`
              : undefined
          }
        />
      </div>
      <DonutCard title="Verdeling portefeuille" kind="saving" rows={donutRows} />
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

function PositionsTable({
  portfolio,
  securities,
  onEdit,
  onViewTransactions,
}: {
  portfolio: Portfolio
  securities: Security[]
  onEdit: (security: Security) => void
  onViewTransactions: (securityId: number, name: string) => void
}) {
  if (portfolio.positions.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center text-sm text-ink-2">
        Nog geen effecten. Voeg er hieronder een toe en log transacties.
      </div>
    )
  }
  const byId = new Map(securities.map((s) => [s.id, s]))
  return (
    <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[880px] text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-ink-3">
            <th className="px-5 py-3 text-left font-medium">Effect</th>
            <th className="px-3 py-3 text-right font-medium">Aantal</th>
            <th className="px-3 py-3 text-right font-medium">Gem. aankoop</th>
            <th className="px-3 py-3 text-right font-medium">Koers</th>
            <th className="px-3 py-3 text-right font-medium">Waarde</th>
            <th className="px-3 py-3 text-right font-medium">Winst/verlies</th>
            <th className="px-3 py-3 text-right font-medium">% port.</th>
            <th className="px-5 py-3" />
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {portfolio.positions.map((p) => (
            <tr key={p.security_id} className="border-b border-line last:border-b-0 hover:bg-raised/50">
              <td className="px-5 py-2">
                {p.name}
                {p.ticker ? (
                  <span className="ml-2 text-xs text-ink-3">{p.ticker}</span>
                ) : (
                  <span className="ml-2 text-xs text-warn">geen ticker</span>
                )}
              </td>
              <td className="px-3 py-2 text-right">{dec(p.shares)}</td>
              <td className="px-3 py-2 text-right text-ink-2">{dec(p.avg_buy_price)}</td>
              <td className="px-3 py-2 text-right text-ink-2">{dec(p.current_price)}</td>
              <td className="px-3 py-2 text-right">
                {p.value_cents !== null ? formatCentsPlain(p.value_cents) : '–'}
              </td>
              <td className="px-3 py-2 text-right">
                {p.gain_cents === null ? (
                  <span className="text-ink-3">–</span>
                ) : (
                  <span className={p.gain_cents < 0 ? 'text-crit' : 'text-good'}>
                    {p.gain_cents > 0 ? '+' : ''}
                    {formatCentsPlain(p.gain_cents)}
                    {p.gain_pct !== null && (
                      <span className="ml-1 text-xs text-ink-3">
                        ({p.gain_pct > 0 ? '+' : ''}
                        {pctFmt.format(p.gain_pct)} %)
                      </span>
                    )}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-right text-ink-3">{pctFmt.format(p.portfolio_pct)} %</td>
              <td className="whitespace-nowrap px-5 py-2 text-right">
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
          ))}
        </tbody>
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
    <section className="grid gap-4 lg:grid-cols-3">
      <SecurityForm contextId={contextId} onSaved={onChanged} />
      <TransactionForm securities={securities} onSaved={onChanged} />
      <PriceForm securities={securities} onSaved={onChanged} />
    </section>
  )
}

function SecurityForm({ contextId, onSaved }: { contextId: number; onSaved: () => void }) {
  const [name, setName] = useState('')
  const [ticker, setTicker] = useState('')
  const [isin, setIsin] = useState('')
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
    }
    try {
      await api<Security>('/api/securities', { method: 'POST', body: JSON.stringify(payload) })
      setName('')
      setTicker('')
      setIsin('')
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
