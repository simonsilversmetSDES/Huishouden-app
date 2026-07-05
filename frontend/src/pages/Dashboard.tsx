import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { CategoryStatus, CategoryType, DashboardData } from '../api/types'
import Meter, { fundingTone, spendingTone, type MeterTone } from '../components/Meter'
import { formatCents, formatMonthYear } from '../lib/format'
import { useAppState } from '../state/AppState'

const TONE_TEXT: Record<MeterTone, string> = {
  accent: 'text-accent',
  good: 'text-good',
  warn: 'text-warn',
  crit: 'text-crit',
}

function toneDot(tone: MeterTone) {
  return (
    <span
      aria-hidden
      className={`inline-block size-2 rounded-full ${
        { accent: 'bg-accent', good: 'bg-good', warn: 'bg-warn', crit: 'bg-crit' }[tone]
      }`}
    />
  )
}

interface Period {
  year: number
  month: number
}

function currentPeriod(): Period {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1 }
}

function shiftPeriod({ year, month }: Period, delta: number): Period {
  const index = year * 12 + (month - 1) + delta
  return { year: Math.floor(index / 12), month: (index % 12) + 1 }
}

export default function Dashboard() {
  const { contextId } = useAppState()
  const [period, setPeriod] = useState<Period>(currentPeriod)
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    api<DashboardData>(
      `/api/dashboard?context_id=${contextId}&year=${period.year}&month=${period.month}`,
    )
      .then(setData)
      .catch(() => setError('Dashboard laden mislukt — probeer opnieuw'))
  }, [contextId, period])

  useEffect(load, [load])

  const now = currentPeriod()
  const isCurrentMonth = period.year === now.year && period.month === now.month

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold capitalize">
          {formatMonthYear(period.year, period.month)}
        </h1>
        <div className="ml-auto flex items-center gap-1">
          {!isCurrentMonth && (
            <button
              onClick={() => setPeriod(currentPeriod())}
              className="rounded-lg px-2.5 py-1.5 text-sm text-ink-3 hover:bg-surface hover:text-ink-2"
            >
              Vandaag
            </button>
          )}
          <button
            onClick={() => setPeriod((p) => shiftPeriod(p, -1))}
            aria-label="Vorige maand"
            className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
          >
            ‹
          </button>
          <button
            onClick={() => setPeriod((p) => shiftPeriod(p, 1))}
            aria-label="Volgende maand"
            className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
          >
            ›
          </button>
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
  const tbaTone: MeterTone = tba === 0 ? 'good' : tba > 0 ? 'accent' : 'crit'
  const tbaLabel =
    tba === 0
      ? 'Alles is verdeeld — zero-based'
      : tba > 0
        ? 'nog niet toegewezen in het budget'
        : 'te veel gepland tegenover het inkomen'

  const totals = new Map(data.type_totals.map((t) => [t.type, t]))
  const inkomen = totals.get('Inkomen')
  const uitgaven = totals.get('Uitgaven')
  const sparen = totals.get('Sparen')

  const hasAnything =
    data.type_totals.some((t) => t.budget_cents !== 0 || t.actual_cents !== 0) ||
    data.uncategorized_count > 0

  return (
    <div className="space-y-4">
      {/* TBA-hero: het belangrijkste cijfer van de maand */}
      <section className="rounded-2xl border border-edge bg-surface p-6">
        <p className="text-sm text-ink-3">Te verdelen (to be allocated)</p>
        <p className="mt-1 text-5xl font-semibold tracking-tight">{formatCents(tba)}</p>
        <p className="mt-3 flex items-center gap-2 text-sm">
          {toneDot(tbaTone)}
          <span className={tba === 0 ? TONE_TEXT.good : 'text-ink-2'}>
            {tba === 0 ? tbaLabel : `${formatCents(Math.abs(tba))} ${tbaLabel}`}
          </span>
        </p>
      </section>

      {/* Budget-status per type */}
      <section className="grid gap-4 sm:grid-cols-3">
        {inkomen && <TypeTile label="Inkomen" total={inkomen} isSpending={false} />}
        {uitgaven && <TypeTile label="Uitgaven" total={uitgaven} isSpending />}
        {sparen && <TypeTile label="Sparen" total={sparen} isSpending={false} />}
      </section>

      {data.uncategorized_count > 0 && (
        <div className="flex items-center gap-2 rounded-2xl border border-edge bg-surface px-4 py-3 text-sm text-ink-2">
          {toneDot('warn')}
          {data.uncategorized_count === 1
            ? '1 transactie zonder categorie deze maand'
            : `${data.uncategorized_count} transacties zonder categorie deze maand`}
        </div>
      )}

      {hasAnything ? (
        <CategoryList categories={data.categories} />
      ) : (
        <section className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center">
          <p className="text-ink-2">Nog geen budget of transacties voor deze maand.</p>
          <p className="mt-2 text-sm text-ink-3">
            Zet je maandbudget op de{' '}
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
  isSpending,
}: {
  label: string
  total: { budget_cents: number; actual_cents: number }
  isSpending: boolean
}) {
  const { budget_cents: budget, actual_cents: actual } = total
  const tone = isSpending ? spendingTone(actual, budget) : fundingTone(actual, budget)
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
      </p>
    </div>
  )
}

const SECTION_ORDER: CategoryType[] = ['Uitgaven', 'Inkomen', 'Sparen']

function CategoryList({ categories }: { categories: CategoryStatus[] }) {
  const visible = categories.filter((c) => c.budget_cents !== 0 || c.actual_cents !== 0)
  const hidden = categories.length - visible.length

  return (
    <section className="rounded-2xl border border-edge bg-surface">
      <h2 className="border-b border-line px-5 py-4 text-sm font-medium text-ink-2">
        Budget vs. werkelijk
      </h2>
      <div className="divide-y divide-line">
        {SECTION_ORDER.map((type) => {
          const rows = visible.filter((c) => c.type === type)
          if (rows.length === 0) return null
          return (
            <div key={type} className="px-5 py-4">
              <h3 className="mb-3 text-xs font-medium uppercase tracking-wide text-ink-3">
                {type}
              </h3>
              <ul className="space-y-3">
                {rows.map((row) => (
                  <CategoryRow key={row.category_id} row={row} />
                ))}
              </ul>
            </div>
          )
        })}
      </div>
      {hidden > 0 && (
        <p className="border-t border-line px-5 py-3 text-xs text-ink-3">
          {hidden} categorieën zonder budget of activiteit verborgen
        </p>
      )}
    </section>
  )
}

function CategoryRow({ row }: { row: CategoryStatus }) {
  const isSpending = row.type === 'Uitgaven'
  const tone = isSpending
    ? spendingTone(row.actual_cents, row.budget_cents)
    : fundingTone(row.actual_cents, row.budget_cents)
  const over = row.actual_cents - row.budget_cents

  return (
    <li>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate">{row.name}</span>
        <span className="shrink-0 text-ink-2">
          {formatCents(row.actual_cents)}
          <span className="text-ink-3"> / {formatCents(row.budget_cents)}</span>
          {isSpending && over > 0 && (
            <span className={`ml-2 ${TONE_TEXT.crit}`}>+{formatCents(over)}</span>
          )}
        </span>
      </div>
      <Meter value={row.actual_cents} max={row.budget_cents} tone={tone} />
    </li>
  )
}
