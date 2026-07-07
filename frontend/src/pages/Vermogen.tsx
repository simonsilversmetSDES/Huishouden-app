import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, ApiError } from '../api/client'
import type { AccountStatus, AccountSnapshotPayload } from '../api/types'
import { seriesColor } from '../lib/chartColors'
import { formatCents, formatCentsPlain, MAAND_KORT, parseEuroToCents } from '../lib/format'
import { useAppState } from '../state/AppState'

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

      {!error && status && status.accounts.length === 0 && (
        <div className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center text-sm text-ink-2">
          Nog geen rekeningen in deze context.
        </div>
      )}

      {!error && status && status.accounts.length > 0 && (
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
          <StatusTable status={status} />
        </>
      )}
    </section>
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
