import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type {
  Portfolio,
  PriceFetchResult,
  Security,
  SecurityPayload,
  SecurityPricePayload,
  SecuritySide,
  SecurityTransactionPayload,
} from '../api/types'
import DonutCard from '../components/DonutCard'
import { formatCents, formatCentsPlain } from '../lib/format'
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
          <PositionsTable portfolio={portfolio} />
          <EntrySection
            contextId={contextId}
            securities={securities}
            onChanged={load}
          />
        </>
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

function PositionsTable({ portfolio }: { portfolio: Portfolio }) {
  if (portfolio.positions.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center text-sm text-ink-2">
        Nog geen effecten. Voeg er hieronder een toe en log transacties.
      </div>
    )
  }
  return (
    <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[820px] text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-ink-3">
            <th className="px-5 py-3 text-left font-medium">Effect</th>
            <th className="px-3 py-3 text-right font-medium">Aantal</th>
            <th className="px-3 py-3 text-right font-medium">Gem. aankoop</th>
            <th className="px-3 py-3 text-right font-medium">Koers</th>
            <th className="px-3 py-3 text-right font-medium">Waarde</th>
            <th className="px-3 py-3 text-right font-medium">Winst/verlies</th>
            <th className="px-5 py-3 text-right font-medium">% port.</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {portfolio.positions.map((p) => (
            <tr key={p.security_id} className="border-b border-line last:border-b-0 hover:bg-raised/50">
              <td className="px-5 py-2">
                {p.name}
                {p.ticker && <span className="ml-2 text-xs text-ink-3">{p.ticker}</span>}
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
              <td className="px-5 py-2 text-right text-ink-3">{pctFmt.format(p.portfolio_pct)} %</td>
            </tr>
          ))}
        </tbody>
      </table>
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
