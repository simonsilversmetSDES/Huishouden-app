import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
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
  ForecastNetWorth,
  NetWorth,
  NetWorthRow,
  NetWorthSummary,
} from '../api/types'
import DonutCard from '../components/DonutCard'
import { ASSET_CLASS_COLORS, ASSET_CLASS_LABEL, seriesColor } from '../lib/chartColors'
import { useChartPress } from '../lib/useChartPress'
import { formatCents, formatCentsPlain, MAAND_KORT, parseEuroToCents } from '../lib/format'
import { useIsMobile } from '../lib/useMediaQuery'
import { useAppState } from '../state/AppState'

const ASSET_CLASSES: AssetClass[] = [
  'contant',
  'etf_fondsen',
  'aandelen',
  'bitcoin',
  'pensioensparen',
  'groepsverzekering',
  'woning',
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
      <NetWorthSection contextId={contextId} />
      <AccountStatusSection contextId={contextId} />
    </div>
  )
}

function AccountStatusSection({ contextId }: { contextId: number }) {
  const { contexts } = useAppState()
  const [activeId, setActiveId] = useState(contextId)
  const [status, setStatus] = useState<AccountStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Volgt de default-context als startpunt, maar blijft nadien onafhankelijk
  // instelbaar — de rekeningen/standen zijn immers per entiteit.
  useEffect(() => setActiveId(contextId), [contextId])

  const load = useCallback(() => {
    setError(null)
    api<AccountStatus>(`/api/account-snapshots?context_id=${activeId}`)
      .then(setStatus)
      .catch(() => setError('Rekeningstatus laden mislukt — probeer opnieuw'))
  }, [activeId])

  useEffect(load, [load])

  return (
    <section>
      <details className="space-y-4">
        <summary className="cursor-pointer text-base font-medium">Rekeningstatus</summary>

      {contexts.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-ink-3">Entiteit:</span>
          {contexts.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setActiveId(c.id)}
              aria-pressed={c.id === activeId}
              className={`rounded-lg border px-3 py-1 text-xs font-medium transition-colors ${
                c.id === activeId
                  ? 'border-accent bg-accent text-white'
                  : 'border-edge text-ink-3 hover:text-ink-2'
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

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
          <AccountsManager contextId={activeId} accounts={status.accounts} onChanged={load} />

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
      </details>
    </section>
  )
}

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: 'zicht', label: 'Zichtrekening' },
  { value: 'spaar', label: 'Spaarrekening' },
  { value: 'pensioensparen', label: 'Pensioensparen' },
  { value: 'groepsverzekering', label: 'Groepsverzekering' },
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
      <div className="mt-4 h-64 max-md:h-56">
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

// Enkel deze activaklassen tellen mee als "belegging" in de Vermogen-tab; de
// detailverdeling per positie staat al in de Beleggingen-tab.
const INVESTMENT_CLASSES: AssetClass[] = ['etf_fondsen', 'aandelen', 'bitcoin']

/** Totaal van een maandrij, eventueel zonder de woning-klasse. */
function rowTotalExcl(row: NetWorthRow, excludeWoning: boolean): number {
  return row.assets
    .filter((a) => !excludeWoning || a.asset_class !== 'woning')
    .reduce((sum, a) => sum + a.value_cents, 0)
}

function NetWorthSection({ contextId }: { contextId: number }) {
  const { contexts } = useAppState()
  const [data, setData] = useState<NetWorth | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [excludeWoning, setExcludeWoning] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([contextId])

  // Volgt de globale context-switcher; binnen de tab kan je meerdere entiteiten optellen.
  useEffect(() => setSelectedIds([contextId]), [contextId])

  const load = useCallback(() => {
    setError(null)
    const url =
      selectedIds.length <= 1
        ? `/api/net-worth?context_id=${selectedIds[0] ?? contextId}`
        : `/api/net-worth/combined?${selectedIds.map((id) => `context_ids=${id}`).join('&')}`
    api<NetWorth>(url)
      .then(setData)
      .catch(() => setError('Vermogensbalans laden mislukt — probeer opnieuw'))
  }, [selectedIds, contextId])

  useEffect(load, [load])

  function toggleContext(id: number) {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.length === 1 ? prev : prev.filter((x) => x !== id)
      // volgorde volgens de contexts-lijst behouden
      return contexts.filter((c) => c.id === id || prev.includes(c.id)).map((c) => c.id)
    })
  }

  const breakdown = (data?.latest_breakdown ?? []).filter(
    (a) => !excludeWoning || a.asset_class !== 'woning',
  )
  // "Balansoverzicht" toont de drie beleggingsklassen (ETF's/fondsen, aandelen,
  // bitcoin) samen als één post "Beleggingen"; de split staat in "Balans beleggingen".
  const investTotalCents = breakdown
    .filter((a) => INVESTMENT_CLASSES.includes(a.asset_class))
    .reduce((sum, a) => sum + a.value_cents, 0)
  const activaRows = [
    ...breakdown
      .filter((a) => !INVESTMENT_CLASSES.includes(a.asset_class))
      .map((a) => ({
        name: ASSET_CLASS_LABEL[a.asset_class],
        cents: a.value_cents,
        color: ASSET_CLASS_COLORS[a.asset_class],
      })),
    ...(investTotalCents > 0
      ? [{ name: 'Beleggingen', cents: investTotalCents, color: ASSET_CLASS_COLORS.etf_fondsen }]
      : []),
  ]
  const investRows = breakdown
    .filter((a) => INVESTMENT_CLASSES.includes(a.asset_class))
    .map((a) => ({
      name: ASSET_CLASS_LABEL[a.asset_class],
      cents: a.value_cents,
      color: ASSET_CLASS_COLORS[a.asset_class],
    }))

  // Totaal + verandering in de weergavelaag herrekend, zodat de "zonder woning"-
  // toggle klopt (de backend levert change altijd op het volledige totaal).
  const rows = data?.rows ?? []
  const totalCents = breakdown.reduce((sum, a) => sum + a.value_cents, 0)
  const lastRow = rows.length > 0 ? rows[rows.length - 1] : undefined
  const prevRow = rows.length > 1 ? rows[rows.length - 2] : undefined
  const changeCents =
    lastRow && prevRow
      ? rowTotalExcl(lastRow, excludeWoning) - rowTotalExcl(prevRow, excludeWoning)
      : null

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-medium">Vermogensbalans</h2>
        {data && rows.length > 0 && (
          <div className="ml-auto inline-flex rounded-lg border border-edge bg-surface p-0.5 text-xs font-medium">
            <button
              type="button"
              onClick={() => setExcludeWoning(false)}
              aria-pressed={!excludeWoning}
              className={`rounded-md px-3 py-1 transition-colors ${
                excludeWoning ? 'text-ink-3 hover:text-ink-2' : 'bg-accent text-white'
              }`}
            >
              Inclusief woning
            </button>
            <button
              type="button"
              onClick={() => setExcludeWoning(true)}
              aria-pressed={excludeWoning}
              className={`rounded-md px-3 py-1 transition-colors ${
                excludeWoning ? 'bg-accent text-white' : 'text-ink-3 hover:text-ink-2'
              }`}
            >
              Zonder woning
            </button>
          </div>
        )}
      </div>

      {contexts.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-ink-3">Entiteiten:</span>
          {contexts.map((c) => {
            const on = selectedIds.includes(c.id)
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => toggleContext(c.id)}
                aria-pressed={on}
                className={`rounded-lg border px-3 py-1 text-xs font-medium transition-colors ${
                  on ? 'border-accent bg-accent text-white' : 'border-edge text-ink-3 hover:text-ink-2'
                }`}
              >
                {c.name}
              </button>
            )
          })}
        </div>
      )}

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
              <p className="text-sm text-ink-3">
                Totaal vermogen{excludeWoning ? ' (zonder woning)' : ''}
              </p>
              <p className="mt-1 text-3xl font-semibold tracking-tight">
                {formatCents(totalCents)}
              </p>
              <p className="mt-2 text-xs text-ink-3">
                {data.latest_date
                  ? `stand van ${monthLabel(data.latest_date)}`
                  : 'nog geen gegevens'}
              </p>
            </div>
            <div className="rounded-2xl border border-edge bg-surface p-5">
              <p className="text-sm text-ink-3">Verandering deze maand</p>
              {changeCents === null ? (
                <p className="mt-1 text-3xl font-semibold tracking-tight text-ink-3">–</p>
              ) : (
                <p
                  className={`mt-1 text-3xl font-semibold tracking-tight ${
                    changeCents < 0 ? 'text-crit' : 'text-good'
                  }`}
                >
                  {changeCents > 0 ? '+' : ''}
                  {formatCents(changeCents)}
                </p>
              )}
              <p className="mt-2 text-xs text-ink-3">t.o.v. de vorige maand</p>
            </div>
          </div>

          {rows.length > 0 && (
            <>
              <VermogenDonuts
                selectedIds={selectedIds}
                excludeWoning={excludeWoning}
                activaRows={activaRows}
                investRows={investRows}
              />
              <NetWorthEvolution
                data={data}
                excludeWoning={excludeWoning}
                selectedIds={selectedIds}
              />
            </>
          )}
        </>
      )}
    </section>
  )
}

type SimpleRow = { name: string; cents: number; color?: string }

/** De vier balansdonuts uit de Excel (spec §9): activasplit, per entiteit, beleggingen, contant.
 * Beleggingen is de activaklasse-verdeling (etf/aandelen/BTC) — het detail per positie
 * staat al in de Beleggingen-tab. Contant wordt per geselecteerde entiteit opgehaald. */
function VermogenDonuts({
  selectedIds,
  excludeWoning,
  activaRows,
  investRows,
}: {
  selectedIds: number[]
  excludeWoning: boolean
  activaRows: SimpleRow[]
  investRows: SimpleRow[]
}) {
  const [summary, setSummary] = useState<NetWorthSummary | null>(null)
  const [contant, setContant] = useState<SimpleRow[]>([])

  useEffect(() => {
    api<NetWorthSummary>('/api/net-worth/summary')
      .then(setSummary)
      .catch(() => setSummary(null))
  }, [])

  useEffect(() => {
    let cancelled = false
    // Contant per rekening (recentste maand), zonder pensioensparen/groepsverzekering.
    Promise.all(
      selectedIds.map((id) =>
        api<AccountStatus>(`/api/account-snapshots?context_id=${id}`).catch(() => null),
      ),
    ).then((list) => {
      if (cancelled) return
      const merged = new Map<string, number>()
      for (const status of list) {
        if (!status) continue
        const typeById = new Map(status.accounts.map((a) => [a.id, a.type]))
        const nameById = new Map(status.accounts.map((a) => [a.id, a.name]))
        const latest = status.rows.at(-1)
        if (!latest) continue
        for (const b of latest.balances) {
          const type = typeById.get(b.account_id)
          if (type === 'pensioensparen' || type === 'groepsverzekering') continue
          const name = nameById.get(b.account_id) ?? '?'
          merged.set(name, (merged.get(name) ?? 0) + b.balance_cents)
        }
      }
      setContant([...merged].map(([name, cents]) => ({ name, cents })))
    })
    return () => {
      cancelled = true
    }
  }, [selectedIds])

  // De "zonder woning"-toggle geldt ook hier: trek per entiteit de woning-waarde af.
  const entityCents = (c: NetWorthSummary['contexts'][number]) =>
    c.total_cents - (excludeWoning ? c.woning_cents : 0)
  const entityRows = (summary?.contexts ?? []).map((c) => ({ name: c.name, cents: entityCents(c) }))
  const householdTotal = (summary?.contexts ?? []).reduce((sum, c) => sum + entityCents(c), 0)
  const selectedTotal = (summary?.contexts ?? [])
    .filter((c) => selectedIds.includes(c.context_id))
    .reduce((sum, c) => sum + entityCents(c), 0)
  const sharePct =
    householdTotal > 0
      ? `selectie = ${pctFmt.format((selectedTotal / householdTotal) * 100)} % van het gezin`
      : undefined

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <DonutCard title="Balansoverzicht" rows={activaRows} maxSegments={7} />
      <DonutCard
        title="Balans per entiteit"
        subtitle={sharePct}
        rows={entityRows}
        kind="saving"
        maxSegments={4}
      />
      <DonutCard title="Balans beleggingen" rows={investRows} kind="saving" maxSegments={3} />
      <DonutCard title="Balans contant geld" rows={contant} kind="saving" maxSegments={6} />
    </div>
  )
}

// Het vroegere woning-invoerformulier is weg: de woning-waarde per persoon wordt
// automatisch afgeleid uit de lening/woning-module (spec §8) — zie de Lening-tab.

function NetWorthEvolution({
  data,
  excludeWoning,
  selectedIds,
}: {
  data: NetWorth
  excludeWoning: boolean
  selectedIds: number[]
}) {
  const [hidden, setHidden] = useState<Set<AssetClass>>(new Set())
  const [fromYear, setFromYear] = useState<number | null>(null)
  const [toYear, setToYear] = useState<number | null>(null)
  // Op mobiel: tooltip enkel tonen zolang je op de grafiek duwt.
  const { tooltipActive, pressHandlers } = useChartPress()

  // Forecast ("Status balans" op de Budget-tab), als gestippelde totaallijn.
  const [showForecast, setShowForecast] = useState(false)
  const [forecast, setForecast] = useState<ForecastNetWorth | null>(null)

  useEffect(() => {
    if (!showForecast) return
    setForecast(null)
    api<ForecastNetWorth>(
      `/api/forecast/net-worth?${selectedIds.map((id) => `context_ids=${id}`).join('&')}`,
    )
      .then(setForecast)
      .catch(() => setForecast(null))
  }, [showForecast, selectedIds])

  const forecastRows = showForecast && forecast ? forecast.rows : []

  const years = useMemo(() => {
    const all = [
      ...data.rows.map((r) => Number(r.snapshot_date.slice(0, 4))),
      ...forecastRows.map((r) => Number(r.snapshot_date.slice(0, 4))),
    ]
    return [...new Set(all)].sort((a, b) => a - b)
  }, [data.rows, forecastRows])

  // Activaklassen die effectief in de data voorkomen, in vaste volgorde; woning
  // valt weg wanneer "zonder woning" bovenaan aan staat.
  const presentClasses = ASSET_CLASSES.filter(
    (ac) =>
      (!excludeWoning || ac !== 'woning') &&
      data.rows.some((r) => r.assets.some((a) => a.asset_class === ac)),
  )
  const shownClasses = presentClasses.filter((ac) => !hidden.has(ac))

  const effFrom = fromYear ?? years[0]
  const effTo = toYear ?? years[years.length - 1]

  const inRange = (r: NetWorthRow) => {
    const y = Number(r.snapshot_date.slice(0, 4))
    return y >= effFrom && y <= effTo
  }

  // Forecast-totalen per maandlabel; het eerste forecastpunt valt samen met de
  // laatste werkelijke maand (verbindingspunt), latere maanden worden extra punten.
  const actualLabels = new Set(data.rows.map((r) => monthLabel(r.snapshot_date)))
  const forecastByLabel = new Map<string, number>()
  const forecastExtra: Record<string, number | string>[] = []
  for (const row of forecastRows.filter(inRange)) {
    const label = monthLabel(row.snapshot_date)
    const total = rowTotalExcl(row, excludeWoning)
    if (actualLabels.has(label)) forecastByLabel.set(label, total)
    else forecastExtra.push({ label, forecast: total })
  }

  const chartData = [
    ...data.rows.filter(inRange).map((r) => {
      const byClass = new Map(r.assets.map((a) => [a.asset_class, a.value_cents]))
      const point: Record<string, number | string> = { label: monthLabel(r.snapshot_date) }
      for (const ac of shownClasses) point[ac] = byClass.get(ac) ?? 0
      const fc = forecastByLabel.get(point.label as string)
      if (fc !== undefined) point.forecast = fc
      return point
    }),
    ...forecastExtra,
  ]

  function toggle(ac: AssetClass) {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(ac)) next.delete(ac)
      else next.add(ac)
      return next
    })
  }

  return (
    <div className="flex flex-col rounded-2xl border border-edge bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h3 className="text-sm font-medium text-ink-2">Nettowaarde-evolutie</h3>
        <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ink-3">
          <input
            type="checkbox"
            checked={showForecast}
            onChange={(e) => setShowForecast(e.target.checked)}
            className="accent-accent"
          />
          Forecast
        </label>
        {years.length > 1 && (
          <div className="ml-auto flex items-center gap-1.5 text-xs text-ink-3">
            <span>van</span>
            <select
              value={effFrom}
              onChange={(e) => setFromYear(Number(e.target.value))}
              className="rounded-md border border-edge bg-page px-1.5 py-1 text-ink-2 focus:border-accent focus:outline-none"
            >
              {years
                .filter((y) => y <= effTo)
                .map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
            </select>
            <span>tot</span>
            <select
              value={effTo}
              onChange={(e) => setToYear(Number(e.target.value))}
              className="rounded-md border border-edge bg-page px-1.5 py-1 text-ink-2 focus:border-accent focus:outline-none"
            >
              {years
                .filter((y) => y >= effFrom)
                .map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
            </select>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1.5">
        {presentClasses.map((ac) => {
          const off = hidden.has(ac)
          return (
            <button
              key={ac}
              type="button"
              onClick={() => toggle(ac)}
              aria-pressed={!off}
              className={`flex items-center gap-1.5 text-xs text-ink-2 transition-opacity ${
                off ? 'opacity-40' : ''
              }`}
            >
              <span
                aria-hidden
                className="size-2.5 rounded-sm"
                style={{ backgroundColor: ASSET_CLASS_COLORS[ac] }}
              />
              <span className={off ? 'line-through' : ''}>{ASSET_CLASS_LABEL[ac]}</span>
            </button>
          )
        })}
      </div>

      <div className="mt-4 h-56">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} {...pressHandlers}>
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
              active={tooltipActive}
              formatter={(value, name) => [
                formatCents(value as number),
                name === 'forecast'
                  ? 'Forecast'
                  : (ASSET_CLASS_LABEL[name as AssetClass] ?? name),
              ]}
              contentStyle={{
                backgroundColor: '#ffffff',
                border: '1px solid rgb(11 11 11 / 0.1)',
                borderRadius: 12,
                fontSize: 12,
              }}
            />
            {shownClasses.map((ac) => (
              <Area
                key={ac}
                type="monotone"
                dataKey={ac}
                stackId="nw"
                stroke={ASSET_CLASS_COLORS[ac]}
                strokeWidth={1}
                fill={ASSET_CLASS_COLORS[ac]}
                fillOpacity={0.8}
                isAnimationActive={false}
              />
            ))}
            {showForecast && (
              <Line
                type="monotone"
                dataKey="forecast"
                stroke="#555550"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                dot={false}
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function StatusTable({ status }: { status: AccountStatus }) {
  const isMobile = useIsMobile()
  const rows = useMemo(() => [...status.rows].reverse(), [status.rows]) // recentste eerst

  if (isMobile) {
    // Mobiele weergave: kaartje per maand met totaal + verandering; de
    // rekeningkolommen zitten in een inklapbare sublijst.
    return (
      <div className="rounded-2xl border border-edge bg-surface">
        <ul className="divide-y divide-line">
          {rows.map((row) => {
            const byAccount = new Map(row.balances.map((b) => [b.account_id, b.balance_cents]))
            return (
              <li key={row.snapshot_date}>
                <details className="group px-4 py-2.5">
                  <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3 [&::-webkit-details-marker]:hidden">
                    <span className="text-sm capitalize">{monthLabel(row.snapshot_date)}</span>
                    <span className="text-right">
                      <span className="block text-sm font-medium tabular-nums">
                        {formatCentsPlain(row.total_cents)}
                      </span>
                      {row.change_cents !== null && (
                        <span
                          className={`block text-xs tabular-nums ${
                            row.change_cents < 0 ? 'text-crit' : 'text-good'
                          }`}
                        >
                          {row.change_cents > 0 ? '+' : ''}
                          {formatCentsPlain(row.change_cents)}
                          {row.change_pct !== null &&
                            ` (${row.change_pct > 0 ? '+' : ''}${pctFmt.format(row.change_pct)} %)`}
                        </span>
                      )}
                    </span>
                  </summary>
                  <ul className="mt-2 space-y-1 border-t border-line pt-2">
                    {status.accounts.map((account) => (
                      <li
                        key={account.id}
                        className="flex items-baseline justify-between gap-3 text-xs"
                      >
                        <span className="min-w-0 truncate text-ink-3">{account.name}</span>
                        <span className="shrink-0 tabular-nums text-ink-2">
                          {byAccount.has(account.id)
                            ? formatCentsPlain(byAccount.get(account.id) as number)
                            : '–'}
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            )
          })}
        </ul>
      </div>
    )
  }

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
