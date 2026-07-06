import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { CategoryStatus, CategoryType, DashboardData, TypeTotal } from '../api/types'
import DonutCard from '../components/DonutCard'
import Meter, { spendingTone, type MeterTone } from '../components/Meter'
import PeriodPicker, { currentPeriod, type Period } from '../components/PeriodPicker'
import TrackedVsBudget from '../components/TrackedVsBudget'
import { formatCents, formatCentsPlain, formatMonthYear } from '../lib/format'
import { useAppState } from '../state/AppState'

const pctFmt = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 1 })

function toneDot(tone: 'good' | 'warn' | 'crit' | 'accent') {
  return (
    <span
      aria-hidden
      className={`inline-block size-2 rounded-full ${
        { accent: 'bg-accent', good: 'bg-good', warn: 'bg-warn', crit: 'bg-crit' }[tone]
      }`}
    />
  )
}

export default function Dashboard() {
  const { contextId } = useAppState()
  const [period, setPeriod] = useState<Period>(() => currentPeriod())
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    const monthParam = period.mode === 'maand' ? `&month=${period.month}` : ''
    api<DashboardData>(`/api/dashboard?context_id=${contextId}&year=${period.year}${monthParam}`)
      .then(setData)
      .catch(() => setError('Dashboard laden mislukt — probeer opnieuw'))
  }, [contextId, period])

  useEffect(load, [load])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold capitalize">
          {period.mode === 'maand' ? formatMonthYear(period.year, period.month) : period.year}
        </h1>
        <div className="ml-auto">
          <PeriodPicker period={period} onChange={setPeriod} />
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {!error && data && <DashboardBody data={data} />}
      {!error && !data && <p className="py-12 text-center text-sm text-ink-3">Laden…</p>}
    </div>
  )
}

function DashboardBody({ data }: { data: DashboardData }) {
  const tba = data.to_be_allocated_cents
  const tbaTone = tba === 0 ? 'good' : tba > 0 ? 'accent' : 'crit'
  const periodWord = data.month === null ? 'dit jaar' : 'deze maand'

  const totals = new Map(data.type_totals.map((t) => [t.type, t]))
  const inkomen = totals.get('Inkomen')
  const uitgaven = totals.get('Uitgaven')
  const sparen = totals.get('Sparen')

  const savingsRate =
    inkomen && sparen && inkomen.actual_cents > 0 && sparen.actual_cents > 0
      ? (sparen.actual_cents / inkomen.actual_cents) * 100
      : null

  const hasAnything =
    data.type_totals.some((t) => t.budget_cents !== 0 || t.actual_cents !== 0) ||
    data.uncategorized_count > 0

  const donutRows = (type: CategoryType) =>
    data.categories
      .filter((c) => c.type === type)
      .map((c) => ({ name: c.name, cents: c.actual_cents }))

  return (
    <div className="space-y-4">
      {/* TBA + type-tegels */}
      <section className="grid gap-4 lg:grid-cols-4">
        <div className="rounded-2xl border border-edge bg-surface p-5">
          <p className="text-sm text-ink-3">Te verdelen</p>
          <p className="mt-1 text-3xl font-semibold tracking-tight">{formatCents(tba)}</p>
          <p className="mt-2 flex items-center gap-2 text-xs text-ink-2">
            {toneDot(tbaTone)}
            {tba === 0
              ? 'alles is verdeeld'
              : tba > 0
                ? `nog niet toegewezen ${periodWord}`
                : `te veel gepland ${periodWord}`}
          </p>
        </div>
        {inkomen && <TypeTile label="Inkomen" total={inkomen} tone="income" />}
        {uitgaven && (
          <TypeTile
            label="Uitgaven"
            total={uitgaven}
            tone={spendingTone(uitgaven.actual_cents, uitgaven.budget_cents)}
          />
        )}
        {sparen && (
          <TypeTile
            label="Sparen"
            total={sparen}
            tone="saving"
            extra={
              savingsRate !== null
                ? `je spaart ${pctFmt.format(savingsRate)} % van je inkomen`
                : undefined
            }
          />
        )}
      </section>

      {data.uncategorized_count > 0 && (
        <div className="flex items-center gap-2 rounded-2xl border border-edge bg-surface px-4 py-3 text-sm text-ink-2">
          {toneDot('warn')}
          {data.uncategorized_count === 1
            ? `1 transactie zonder categorie ${periodWord}`
            : `${data.uncategorized_count} transacties zonder categorie ${periodWord}`}
        </div>
      )}

      {hasAnything ? (
        <>
          {/* Grafieken zoals in de Excel */}
          <section className="grid gap-4 lg:grid-cols-2">
            <DonutCard title="Inkomen per categorie" kind="income" rows={donutRows('Inkomen')} />
            <TrackedVsBudget months={data.months} selectedMonth={data.month} />
            <DonutCard
              title="Uitgaven per categorie"
              kind="expense"
              rows={donutRows('Uitgaven')}
            />
            <DonutCard title="Sparen per categorie" kind="saving" rows={donutRows('Sparen')} />
          </section>

          <CategoryTable categories={data.categories} />
        </>
      ) : (
        <section className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center">
          <p className="text-ink-2">Nog geen budget of transacties in deze periode.</p>
          <p className="mt-2 text-sm text-ink-3">
            Zet je budget op de{' '}
            <Link to="/budget" className="text-accent hover:underline">
              Budget-pagina
            </Link>
            .
          </p>
        </section>
      )}
    </div>
  )
}

function TypeTile({
  label,
  total,
  tone,
  extra,
}: {
  label: string
  total: TypeTotal
  tone: MeterTone
  extra?: string
}) {
  const { budget_cents: budget, actual_cents: actual } = total
  const pct = budget > 0 ? Math.round((actual / budget) * 100) : null
  return (
    <div className="rounded-2xl border border-edge bg-surface p-5">
      <div className="flex items-baseline justify-between">
        <p className="text-sm text-ink-3">{label}</p>
        {pct !== null && <p className="text-xs text-ink-3">{pct} %</p>}
      </div>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{formatCents(actual)}</p>
      <div className="mt-3">
        <Meter value={actual} max={budget} tone={tone} />
      </div>
      <p className="mt-2 text-xs text-ink-3">
        {budget > 0 ? `van ${formatCents(budget)} gebudgetteerd` : 'geen budget ingesteld'}
        {extra ? ` · ${extra}` : ''}
      </p>
    </div>
  )
}

const SECTION_ORDER: CategoryType[] = ['Inkomen', 'Uitgaven', 'Sparen']

function CategoryTable({ categories }: { categories: CategoryStatus[] }) {
  const visible = categories.filter((c) => c.budget_cents !== 0 || c.actual_cents !== 0)
  const hidden = categories.length - visible.length

  return (
    <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-ink-3">
            <th className="px-5 py-3 text-left font-medium">Budget vs. werkelijk</th>
            <th className="px-3 py-3 text-right font-medium">Werkelijk</th>
            <th className="px-3 py-3 text-right font-medium">Budget</th>
            <th className="px-3 py-3 text-right font-medium">%</th>
            <th className="px-3 py-3 text-right font-medium">Resterend</th>
            <th className="px-5 py-3 text-right font-medium">Boven budget</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {SECTION_ORDER.map((type) => {
            const rows = visible.filter((c) => c.type === type)
            if (rows.length === 0) return null
            return (
              <SectionRows key={type} type={type} rows={rows} />
            )
          })}
        </tbody>
      </table>
      {hidden > 0 && (
        <p className="border-t border-line px-5 py-3 text-xs text-ink-3">
          {hidden} categorieën zonder budget of activiteit verborgen
        </p>
      )}
    </section>
  )
}

function SectionRows({ type, rows }: { type: CategoryType; rows: CategoryStatus[] }) {
  const sum = (f: (r: CategoryStatus) => number) => rows.reduce((acc, r) => acc + f(r), 0)
  return (
    <>
      <tr>
        <td
          colSpan={6}
          className="px-5 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-ink-3"
        >
          {type}
        </td>
      </tr>
      {rows.map((row) => (
        <TableRow key={row.category_id} row={row} />
      ))}
      <tr className="border-b border-line last:border-b-0">
        <td className="px-5 py-2 text-xs text-ink-3">Totaal {type.toLowerCase()}</td>
        <td className="px-3 py-2 text-right text-xs font-medium">
          {formatCentsPlain(sum((r) => r.actual_cents))}
        </td>
        <td className="px-3 py-2 text-right text-xs text-ink-2">
          {formatCentsPlain(sum((r) => r.budget_cents))}
        </td>
        <td className="px-3 py-2 text-right text-xs text-ink-2">
          {pctText(sum((r) => r.actual_cents), sum((r) => r.budget_cents))}
        </td>
        <td className="px-3 py-2" />
        <td className="px-5 py-2" />
      </tr>
    </>
  )
}

function pctText(actual: number, budget: number): string {
  return budget > 0 ? `${Math.round((actual / budget) * 100)} %` : '–'
}

function TableRow({ row }: { row: CategoryStatus }) {
  const isSpending = row.type === 'Uitgaven'
  const tone: MeterTone = isSpending
    ? spendingTone(row.actual_cents, row.budget_cents)
    : row.type === 'Inkomen'
      ? 'income'
      : 'saving'
  const pct = row.budget_cents > 0 ? Math.round((row.actual_cents / row.budget_cents) * 100) : null
  const remaining = Math.max(row.budget_cents - row.actual_cents, 0)
  const excess = Math.max(row.actual_cents - row.budget_cents, 0)
  const pctClass =
    pct === null
      ? 'text-ink-3'
      : isSpending && pct > 100
        ? 'font-medium text-crit'
        : !isSpending && pct >= 100
          ? 'font-medium text-good'
          : 'text-ink-2'

  return (
    <tr className="hover:bg-raised/50">
      <td className="px-5 py-1.5">
        <span className="block truncate">{row.name}</span>
        <div className="mt-1 max-w-44">
          <Meter value={row.actual_cents} max={row.budget_cents} tone={tone} />
        </div>
      </td>
      <td className="px-3 py-1.5 text-right align-top">{formatCentsPlain(row.actual_cents)}</td>
      <td className="px-3 py-1.5 text-right align-top text-ink-2">
        {row.budget_cents !== 0 ? formatCentsPlain(row.budget_cents) : '–'}
      </td>
      <td className={`px-3 py-1.5 text-right align-top ${pctClass}`}>
        {pct !== null ? `${pct} %` : '–'}
      </td>
      <td className="px-3 py-1.5 text-right align-top text-ink-2">
        {row.budget_cents > 0 && remaining > 0 ? formatCentsPlain(remaining) : '–'}
      </td>
      <td
        className={`px-5 py-1.5 text-right align-top ${
          excess > 0 ? (isSpending ? 'text-crit' : 'text-good') : 'text-ink-2'
        }`}
      >
        {excess > 0 ? formatCentsPlain(excess) : '–'}
      </td>
    </tr>
  )
}
