import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, ApiError } from '../api/client'
import type {
  AccountPayload,
  AccountSnapshotPayload,
  AccountStatus,
  AccountType,
  AssetClass,
  NetWorth,
  NetWorthPayload,
} from '../api/types'
import DonutCard from '../components/DonutCard'
import { ASSET_CLASS_COLORS, ASSET_CLASS_LABEL, seriesColor } from '../lib/chartColors'
import { formatCents, formatCentsPlain, MAAND_KORT, parseEuroToCents } from '../lib/format'
import { useAppState } from '../state/AppState'

const ASSET_CLASSES: AssetClass[] = [
  'contant',
  'etf_fondsen',
  'pensioensparen',
  'groepsverzekering',
  'woning',
  'aandelen',
]

const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'

// nl-BE-getalassen zoals op het dashboard (TrackedVsBudget).
const euroInt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 0 })
const pctFmt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 1 })

function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

/** ISO-datum ("2025-02-01") → "feb 25" voor de grafiekas. */
function monthLabel(iso: string): string {
  const [y, m] = iso.split('-')
  return `${MAAND_KORT[Number(m) - 1]} ${y.slice(2)}`
}

export default function Vermogen() {
  const { contextId } = useAppState()

  if (contextId === null) return null

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Vermogen</h1>
      <AccountStatusSection contextId={contextId} />
      <NetWorthSection contextId={contextId} />
    </div>
  )
}

function AccountStatusSection({ contextId }: { contextId: number }) {
  const [status, setStatus] = useState<AccountStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    api<AccountStatus>(`/api/account-snapshots?context_id=${contextId}`)
      .then(setStatus)
      .catch(() => setError('Rekeningstatus laden mislukt — probeer opnieuw'))
  }, [contextId])

  useEffect(load, [load])

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-medium">Rekeningstatus</h2>
      </div>

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {!error && status && (
        <>
          <AccountsManager contextId={contextId} accounts={status.accounts} onChanged={load} />

          {status.accounts.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center text-sm text-ink-2">
              Voeg hierboven rekeningen toe om maandstanden in te voeren.
            </div>
          ) : (
            <>
              {status.missing_current_month && (
                <div className="flex items-center gap-2 rounded-2xl border border-warn/40 bg-surface px-4 py-3 text-sm text-ink-2">
                  <span aria-hidden className="inline-block size-2 rounded-full bg-warn" />
                  {status.missing_account_ids.length === status.accounts.length
                    ? 'Nog geen enkele rekeningstand voor deze maand ingevuld.'
                    : `${status.missing_account_ids.length} rekening(en) missen de stand van deze maand.`}
                </div>
              )}

              <SnapshotForm status={status} onSaved={load} />
              <AccountEvolution status={status} />
              <details className="rounded-2xl border border-edge bg-surface">
                <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-ink-2">
                  Alle maandstanden
                </summary>
                <StatusTable status={status} />
              </details>
            </>
          )}
        </>
      )}
    </section>
  )
}

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: 'zicht', label: 'Zichtrekening' },
  { value: 'spaar', label: 'Spaarrekening' },
  { value: 'belegging', label: 'Belegging' },
  { value: 'andere', label: 'Andere' },
]

function AccountsManager({
  contextId,
  accounts,
  onChanged,
}: {
  contextId: number
  accounts: AccountStatus['accounts']
  onChanged: () => void
}) {
  const [name, setName] = useState('')
  const [type, setType] = useState<AccountType>('zicht')
  const [error, setError] = useState<string | null>(null)

  async function add(e: FormEvent) {
    e.preventDefault()
    if (name.trim() === '') {
      setError('Naam is verplicht')
      return
    }
    setError(null)
    const payload: AccountPayload = { context_id: contextId, name: name.trim(), type }
    try {
      await api('/api/accounts', { method: 'POST', body: JSON.stringify(payload) })
      setName('')
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Toevoegen mislukt')
    }
  }

  async function rename(id: number, current: string, accType: AccountType) {
    const next = window.prompt('Nieuwe naam voor de rekening:', current)
    if (next === null || next.trim() === '' || next.trim() === current) return
    const payload: AccountPayload = { context_id: contextId, name: next.trim(), type: accType }
    await api(`/api/accounts/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
    onChanged()
  }

  async function remove(id: number, accName: string) {
    if (!window.confirm(`Rekening "${accName}" verwijderen? De historiek blijft bewaard.`)) return
    await api(`/api/accounts/${id}`, { method: 'DELETE' })
    onChanged()
  }

  return (
    <details className="rounded-2xl border border-edge bg-surface">
      <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-ink-2">
        Rekeningen beheren
      </summary>
      <div className="space-y-3 border-t border-line px-5 py-4">
        {accounts.length > 0 && (
          <ul className="space-y-1.5 text-sm">
            {accounts.map((a) => (
              <li key={a.id} className="flex items-center gap-2">
                <span className="truncate">{a.name}</span>
                <span className="text-xs text-ink-3">{a.type}</span>
                <span className="ml-auto flex gap-3">
                  <button
                    onClick={() => void rename(a.id, a.name, a.type)}
                    className="text-xs text-ink-3 hover:text-ink-2 hover:underline"
                  >
                    Hernoemen
                  </button>
                  <button
                    onClick={() => void remove(a.id, a.name)}
                    className="text-xs text-ink-3 hover:text-crit hover:underline"
                  >
                    Verwijderen
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={add} className="flex flex-wrap items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nieuwe rekening (bv. Vrije ruimte Degiro)"
            className="flex-1 rounded-lg border border-edge bg-page px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
          />
          <select
            value={type}
            onChange={(e) => setType(e.target.value as AccountType)}
            className="rounded-lg border border-edge bg-page px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
          >
            {ACCOUNT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/85"
          >
            Toevoegen
          </button>
          {error && <span className="text-sm text-crit">{error}</span>}
        </form>
      </div>
    </details>
  )
}

function SnapshotForm({ status, onSaved }: { status: AccountStatus; onSaved: () => void }) {
  const [month, setMonth] = useState(currentMonth)
  const [amounts, setAmounts] = useState<Record<number, string>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const snapshotDate = `${month}-01`

  // Prefill met de bestaande standen van de gekozen maand (bijwerken i.p.v. leeg).
  useEffect(() => {
    const row = status.rows.find((r) => r.snapshot_date === snapshotDate)
    const next: Record<number, string> = {}
    for (const account of status.accounts) {
      const bal = row?.balances.find((b) => b.account_id === account.id)
      next[account.id] = bal ? formatCentsPlain(bal.balance_cents) : ''
    }
    setAmounts(next)
  }, [snapshotDate, status])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const payloads: AccountSnapshotPayload[] = []
    for (const account of status.accounts) {
      const text = (amounts[account.id] ?? '').trim()
      if (text === '') continue
      const cents = parseEuroToCents(text)
      if (cents === null) {
        setError(`Ongeldig bedrag bij ${account.name}`)
        return
      }
      payloads.push({ account_id: account.id, snapshot_date: snapshotDate, balance_cents: cents })
    }
    if (payloads.length === 0) {
      setError('Vul minstens één rekeningstand in')
      return
    }
    setSaving(true)
    try {
      for (const payload of payloads) {
        await api<AccountStatus>('/api/account-snapshots', {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt — probeer opnieuw')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium">Maandstand invoeren of bijwerken</h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Maand</span>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className={inputClass}
          />
        </label>
        {status.accounts.map((account) => (
          <label key={account.id} className="block">
            <span className="mb-1 block truncate text-xs uppercase tracking-wide text-ink-3">
              {account.name}
            </span>
            <input
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              value={amounts[account.id] ?? ''}
              onChange={(e) => setAmounts((a) => ({ ...a, [account.id]: e.target.value }))}
              className={`${inputClass} text-right tabular-nums`}
            />
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
        >
          {saving ? 'Bezig…' : 'Opslaan'}
        </button>
        {error && <p className="text-sm text-crit">{error}</p>}
      </div>
    </form>
  )
}

function AccountEvolution({ status }: { status: AccountStatus }) {
  const data = status.rows.map((row) => {
    const byAccount = new Map(row.balances.map((b) => [b.account_id, b.balance_cents]))
    return {
      label: monthLabel(row.snapshot_date),
      ...Object.fromEntries(status.accounts.map((a) => [String(a.id), byAccount.get(a.id) ?? 0])),
    }
  })

  if (data.length === 0) {
    return (
      <div className="rounded-2xl border border-edge bg-surface p-8 text-center text-sm text-ink-3">
        Nog geen standen ingevoerd.
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-edge bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-ink-2">Evolutie per rekening</h3>
        <div className="ml-auto flex flex-wrap gap-3">
          {status.accounts.map((account, i) => (
            <span key={account.id} className="flex items-center gap-1.5 text-xs text-ink-2">
              <span
                aria-hidden
                className="size-2.5 rounded-sm"
                style={{ backgroundColor: seriesColor(i) }}
              />
              {account.name}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barCategoryGap="22%">
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
              width={52}
              tick={{ fill: '#898781', fontSize: 11 }}
              tickFormatter={(cents: number) => euroInt.format(cents / 100)}
            />
            <Tooltip
              cursor={{ fill: 'rgb(11 11 11 / 0.04)' }}
              formatter={(value, name) => {
                const account = status.accounts.find((a) => String(a.id) === name)
                return [formatCents(value as number), account?.name ?? name]
              }}
              contentStyle={{
                backgroundColor: '#ffffff',
                border: '1px solid rgb(11 11 11 / 0.1)',
                borderRadius: 12,
                fontSize: 12,
              }}
            />
            {status.accounts.map((account, i) => (
              <Bar
                key={account.id}
                dataKey={String(account.id)}
                stackId="saldo"
                fill={seriesColor(i)}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function NetWorthSection({ contextId }: { contextId: number }) {
  const [data, setData] = useState<NetWorth | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    api<NetWorth>(`/api/net-worth?context_id=${contextId}`)
      .then(setData)
      .catch(() => setError('Vermogensbalans laden mislukt — probeer opnieuw'))
  }, [contextId])

  useEffect(load, [load])

  const donutRows = (data?.latest_breakdown ?? []).map((a) => ({
    name: ASSET_CLASS_LABEL[a.asset_class],
    cents: a.value_cents,
    color: ASSET_CLASS_COLORS[a.asset_class],
  }))

  return (
    <section className="space-y-4">
      <h2 className="text-base font-medium">Vermogensbalans</h2>

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {!error && data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-edge bg-surface p-5">
              <p className="text-sm text-ink-3">Totaal vermogen</p>
              <p className="mt-1 text-3xl font-semibold tracking-tight">
                {formatCents(data.latest_total_cents)}
              </p>
              <p className="mt-2 text-xs text-ink-3">
                {data.latest_date
                  ? `stand van ${monthLabel(data.latest_date)}`
                  : 'nog geen gegevens'}
              </p>
            </div>
            <div className="rounded-2xl border border-edge bg-surface p-5">
              <p className="text-sm text-ink-3">Verandering deze maand</p>
              {data.latest_change_cents === null ? (
                <p className="mt-1 text-3xl font-semibold tracking-tight text-ink-3">–</p>
              ) : (
                <p
                  className={`mt-1 text-3xl font-semibold tracking-tight ${
                    data.latest_change_cents < 0 ? 'text-crit' : 'text-good'
                  }`}
                >
                  {data.latest_change_cents > 0 ? '+' : ''}
                  {formatCents(data.latest_change_cents)}
                </p>
              )}
              <p className="mt-2 text-xs text-ink-3">t.o.v. de vorige maand</p>
            </div>
          </div>

          <NetWorthForm contextId={contextId} data={data} onSaved={load} />

          {data.rows.length > 0 && (
            <div className="grid gap-4 lg:grid-cols-2">
              <DonutCard title="Verdeling activa" rows={donutRows} maxSegments={6} />
              <NetWorthEvolution data={data} />
            </div>
          )}
        </>
      )}
    </section>
  )
}

function NetWorthForm({
  contextId,
  data,
  onSaved,
}: {
  contextId: number
  data: NetWorth
  onSaved: () => void
}) {
  const [month, setMonth] = useState(currentMonth)
  const [assetClass, setAssetClass] = useState<AssetClass>('contant')
  const [amountText, setAmountText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const snapshotDate = `${month}-01`

  // Prefill met de bestaande waarde van (maand, activaklasse).
  useEffect(() => {
    const row = data.rows.find((r) => r.snapshot_date === snapshotDate)
    const asset = row?.assets.find((a) => a.asset_class === assetClass)
    setAmountText(asset ? formatCentsPlain(asset.value_cents) : '')
  }, [snapshotDate, assetClass, data])

  async function submit(e: FormEvent) {
    e.preventDefault()
    const cents = parseEuroToCents(amountText)
    if (cents === null) {
      setError('Ongeldig bedrag')
      return
    }
    setError(null)
    setSaving(true)
    const payload: NetWorthPayload = {
      context_id: contextId,
      snapshot_date: snapshotDate,
      asset_class: assetClass,
      value_cents: cents,
    }
    try {
      await api<NetWorth>('/api/net-worth', { method: 'PUT', body: JSON.stringify(payload) })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt — probeer opnieuw')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium">Activaklasse invoeren of bijwerken</h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Maand</span>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Activaklasse</span>
          <select
            value={assetClass}
            onChange={(e) => setAssetClass(e.target.value as AssetClass)}
            className={inputClass}
          >
            {ASSET_CLASSES.map((ac) => (
              <option key={ac} value={ac}>
                {ASSET_CLASS_LABEL[ac]}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Waarde</span>
          <input
            type="text"
            inputMode="decimal"
            placeholder="0,00"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            className={`${inputClass} text-right tabular-nums`}
          />
        </label>
        <div className="flex items-end gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
          >
            {saving ? 'Bezig…' : 'Opslaan'}
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-crit">{error}</p>}
    </form>
  )
}

function NetWorthEvolution({ data }: { data: NetWorth }) {
  const series = data.rows.map((r) => ({ label: monthLabel(r.snapshot_date), total: r.total_cents }))
  return (
    <div className="flex flex-col rounded-2xl border border-edge bg-surface p-5">
      <h3 className="text-sm font-medium text-ink-2">Nettowaarde-evolutie</h3>
      <div className="mt-4 h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series}>
            <defs>
              <linearGradient id="nwFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2a78d6" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#2a78d6" stopOpacity={0.02} />
              </linearGradient>
            </defs>
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
              width={52}
              tick={{ fill: '#898781', fontSize: 11 }}
              tickFormatter={(cents: number) => euroInt.format(cents / 100)}
            />
            <Tooltip
              formatter={(value) => [formatCents(value as number), 'Nettowaarde']}
              contentStyle={{
                backgroundColor: '#ffffff',
                border: '1px solid rgb(11 11 11 / 0.1)',
                borderRadius: 12,
                fontSize: 12,
              }}
            />
            <Area
              type="monotone"
              dataKey="total"
              stroke="#2a78d6"
              strokeWidth={2}
              fill="url(#nwFill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function StatusTable({ status }: { status: AccountStatus }) {
  const rows = useMemo(() => [...status.rows].reverse(), [status.rows]) // recentste eerst
  return (
    <div className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-ink-3">
            <th className="px-5 py-3 text-left font-medium">Maand</th>
            {status.accounts.map((account) => (
              <th key={account.id} className="px-3 py-3 text-right font-medium">
                {account.name}
              </th>
            ))}
            <th className="px-3 py-3 text-right font-medium">Totaal</th>
            <th className="px-5 py-3 text-right font-medium">Verandering</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((row) => {
            const byAccount = new Map(row.balances.map((b) => [b.account_id, b.balance_cents]))
            return (
              <tr key={row.snapshot_date} className="border-b border-line last:border-b-0">
                <td className="whitespace-nowrap px-5 py-2 capitalize">
                  {monthLabel(row.snapshot_date)}
                </td>
                {status.accounts.map((account) => (
                  <td key={account.id} className="px-3 py-2 text-right text-ink-2">
                    {byAccount.has(account.id)
                      ? formatCentsPlain(byAccount.get(account.id) as number)
                      : '–'}
                  </td>
                ))}
                <td className="px-3 py-2 text-right font-medium">
                  {formatCentsPlain(row.total_cents)}
                </td>
                <td className="whitespace-nowrap px-5 py-2 text-right">
                  {row.change_cents === null ? (
                    <span className="text-ink-3">–</span>
                  ) : (
                    <span className={row.change_cents < 0 ? 'text-crit' : 'text-good'}>
                      {row.change_cents > 0 ? '+' : ''}
                      {formatCentsPlain(row.change_cents)}
                      {row.change_pct !== null && (
                        <span className="ml-1 text-xs text-ink-3">
                          ({row.change_pct > 0 ? '+' : ''}
                          {pctFmt.format(row.change_pct)} %)
                        </span>
                      )}
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
