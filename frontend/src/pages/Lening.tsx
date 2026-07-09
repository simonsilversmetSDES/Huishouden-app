import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type {
  LoanContributionPayload,
  LoanInvestmentPayload,
  LoanKpis,
  LoanOverview,
  LoanPayload,
  LoanScheduleRow,
  Ownership,
  PropertyValuation,
} from '../api/types'
import Meter, { type MeterTone } from '../components/Meter'
import { seriesColor } from '../lib/chartColors'
import { formatCents, formatCentsPlain, formatDate, parseEuroToCents } from '../lib/format'
import { useAppState } from '../state/AppState'

const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'

const pct1 = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 1 })
const pct2 = new Intl.NumberFormat('nl-BE', { maximumFractionDigits: 2 })

/** "0.0251" → "2,51" voor weergave. */
function rateToPct(rate: string): string {
  return pct2.format(Number(rate) * 100)
}

/** Percent-invoer ("2,51" / "2.51") → exacte rate-string "0.0251"; null bij ongeldig. */
function pctToRate(input: string): string | null {
  const t = input.trim().replace(',', '.')
  if (t === '' || !/^\d+(\.\d+)?$/.test(t)) return null
  return String(Number(t) / 100)
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export default function Lening() {
  const [overview, setOverview] = useState<LoanOverview | null>(null)
  const [configured, setConfigured] = useState<boolean | null>(null) // null = nog aan het laden
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api<LoanOverview>('/api/loan')
      .then((data) => {
        setOverview(data)
        setConfigured(true)
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setConfigured(false)
        } else {
          setError('Lening laden mislukt — probeer opnieuw')
        }
      })
  }, [])

  useEffect(load, [load])

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Lening &amp; woning</h1>

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {configured === false && !error && (
        <div className="rounded-2xl border border-dashed border-edge bg-surface p-8 text-center">
          <p className="text-ink-2">Nog geen lening ingesteld.</p>
          <button
            onClick={() => setEditing(true)}
            className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/85"
          >
            Lening instellen
          </button>
        </div>
      )}

      {configured && overview && (
        <>
          <HeroCard
            name={overview.loan.name}
            kpis={overview.kpis}
            valuation={overview.valuation}
            onEdit={() => setEditing(true)}
          />
          <MonthAndTermRow kpis={overview.kpis} schedule={overview.schedule} />
          <PaidBlock kpis={overview.kpis} />
          <div className="grid gap-4 lg:grid-cols-2">
            {overview.valuation && (
              <WoningBlock valuation={overview.valuation} overview={overview} />
            )}
            {overview.ownership && <OwnershipBlock ownership={overview.ownership} />}
          </div>
          <ScheduleTable rows={overview.schedule} />
        </>
      )}

      {editing && (
        <LoanForm
          initial={overview}
          onCancel={() => setEditing(false)}
          onSaved={(data) => {
            setOverview(data)
            setConfigured(true)
            setEditing(false)
          }}
        />
      )}
    </div>
  )
}

// Donkergroene hero zoals de referentie-app: netto waarde = schatting − openstaand,
// met de aflossingsvoortgang als balk. Bewust één donker accentvlak op het lichte thema.
function HeroCard({
  name,
  kpis,
  valuation,
  onEdit,
}: {
  name: string
  kpis: LoanKpis
  valuation: PropertyValuation | null
  onEdit: () => void
}) {
  const netto = valuation ? valuation.estimate_cents - kpis.outstanding_cents : null
  const paidPct = kpis.principal_paid_pct * 100
  return (
    <section className="rounded-2xl bg-[#174f37] p-5 text-white">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-widest text-white/60">{name}</p>
        <button
          onClick={onEdit}
          className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/90 transition-colors hover:bg-white/20"
        >
          ✎ Bewerk
        </button>
      </div>

      {netto !== null && valuation ? (
        <>
          <p className="mt-1 text-sm text-white/70">Netto waarde</p>
          <p className="text-3xl font-semibold tracking-tight">{formatCents(netto)}</p>
          <p className="mt-1 text-xs text-white/60">
            schatting {formatCents(valuation.estimate_cents)} − openstaand{' '}
            {formatCents(kpis.outstanding_cents)}
          </p>
        </>
      ) : (
        <>
          <p className="mt-1 text-sm text-white/70">Openstaand saldo</p>
          <p className="text-3xl font-semibold tracking-tight">
            {formatCents(kpis.outstanding_cents)}
          </p>
        </>
      )}

      <div className="mt-4 flex items-baseline justify-between text-xs text-white/80">
        <span>Afbetaald {formatCents(kpis.paid_principal_cents)}</span>
        <span>Openstaand {formatCents(kpis.outstanding_cents)}</span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-white/20">
        <div
          className="h-full rounded-full bg-[#69c88f] transition-[width] duration-300"
          style={{ width: `${Math.min(paidPct, 100)}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-white/70">
        {pct1.format(paidPct)} % van de lening afgelost
      </p>
    </section>
  )
}

// Maandbedrag (met kapitaal/interest-chips van de eerstvolgende aflossing) naast
// de resterende looptijd, zoals de referentie-app.
function MonthAndTermRow({ kpis, schedule }: { kpis: LoanKpis; schedule: LoanScheduleRow[] }) {
  const next = schedule.find((r) => !r.paid) ?? schedule[schedule.length - 1]
  return (
    <section className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-2xl border border-edge bg-surface p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-3">Maandbedrag</p>
        <p className="mt-1 text-2xl font-semibold tracking-tight">
          {formatCents(kpis.monthly_payment_cents)}
        </p>
        {next && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-good/10 px-2.5 py-1 text-good">
              ● {formatCents(next.principal_cents)} kapitaal
            </span>
            <span className="rounded-full bg-warn/10 px-2.5 py-1 text-warn">
              ● {formatCents(next.interest_cents)} interest
            </span>
          </div>
        )}
      </div>
      <div className="rounded-2xl border border-edge bg-surface p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-3">
          Resterende looptijd
        </p>
        <p className="mt-1 text-2xl font-semibold tracking-tight">{kpis.remaining_label}</p>
        <p className="mt-3 text-xs text-ink-3">
          {kpis.remaining_months} maanden · einddatum {formatDate(kpis.end_date)} ·{' '}
          {pct1.format(kpis.elapsed_pct * 100)} % verstreken
        </p>
      </div>
    </section>
  )
}

// "Totaal afbetaald" met een voortgangsbalk per component, zoals de Excel
// (maandlast/kapitaal/interesten, elk t.o.v. hun totaal over de hele looptijd).
function PaidMeterRow({
  label,
  paid,
  total,
  tone,
}: {
  label: string
  paid: number
  total: number
  tone: MeterTone
}) {
  const pct = total > 0 ? (paid / total) * 100 : 0
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink-2">{label}</span>
        <span className="tabular-nums">
          <span className="font-medium">{formatCents(paid)}</span>
          <span className="ml-1.5 text-xs text-ink-3">van {formatCentsPlain(total)}</span>
          <span className="ml-2 text-xs font-medium text-ink-2">{pct1.format(pct)} %</span>
        </span>
      </div>
      <div className="mt-1">
        <Meter value={paid} max={total} tone={tone} />
      </div>
    </div>
  )
}

function PaidBlock({ kpis }: { kpis: LoanKpis }) {
  return (
    <section className="rounded-2xl border border-edge bg-surface p-5">
      <h2 className="text-base font-medium">Totaal afbetaald</h2>
      <div className="mt-4 space-y-4">
        <PaidMeterRow
          label="Maandlasten"
          paid={kpis.paid_payment_cents}
          total={kpis.total_payment_cents}
          tone="accent"
        />
        <PaidMeterRow
          label="Kapitaal"
          paid={kpis.paid_principal_cents}
          total={kpis.total_principal_cents}
          tone="income"
        />
        <PaidMeterRow
          label="Interesten"
          paid={kpis.paid_interest_cents}
          total={kpis.total_interest_cents}
          tone="expense"
        />
      </div>
    </section>
  )
}

function WoningBlock({
  valuation,
  overview,
}: {
  valuation: PropertyValuation
  overview: LoanOverview
}) {
  const surplusTone = valuation.surplus_cents < 0 ? 'text-crit' : 'text-good'
  const investments = overview.loan.investments
  return (
    <div className="rounded-2xl border border-edge bg-surface p-5">
      <h2 className="text-base font-medium">Woning</h2>
      <div className="mt-3 space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-ink-2">Geschatte waarde (incl. meerwaarde)</span>
          <span className="tabular-nums font-medium">{formatCents(valuation.estimate_cents)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-ink-2">Betaalde prijs (incl. kosten)</span>
          <span className="tabular-nums">{formatCents(valuation.price_paid_cents)}</span>
        </div>
        <div className="flex justify-between border-t border-line pt-1">
          <span className="text-ink-2">Meerwaarde</span>
          <span className={`tabular-nums font-medium ${surplusTone}`}>
            {valuation.surplus_cents > 0 ? '+' : ''}
            {formatCents(valuation.surplus_cents)}
            {valuation.surplus_pct !== null && (
              <span className="ml-1 text-xs text-ink-3">
                ({pct2.format(valuation.surplus_pct * 100)} %)
              </span>
            )}
          </span>
        </div>
      </div>

      {investments.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-3">
            Investeringen aan de woning
          </p>
          <ul className="mt-2 space-y-2 text-sm">
            {investments.map((inv) => (
              <li key={inv.id} className="flex items-baseline justify-between gap-3">
                <span>
                  <span className="text-ink-2">{inv.label}</span>
                  {inv.comment && <span className="block text-xs text-ink-3">{inv.comment}</span>}
                </span>
                <span className="shrink-0 tabular-nums">{formatCentsPlain(inv.added_value_cents)}</span>
              </li>
            ))}
            <li className="flex justify-between border-t border-line pt-1.5 text-xs">
              <span className="text-ink-3">Totaal meerwaarde uit investeringen</span>
              <span className="tabular-nums font-medium">
                {formatCentsPlain(valuation.investments_total_cents)}
              </span>
            </li>
          </ul>
        </div>
      )}
    </div>
  )
}

// Eigendomsverdeling met een gestapelde balk (aandeel per persoon in de totale
// equity) en per persoon de formule-uitleg, zoals de referentie-app.
function OwnershipBlock({ ownership }: { ownership: Ownership }) {
  const totalEquity = ownership.owners.reduce((sum, o) => sum + o.equity_incl_surplus_cents, 0)
  const n = ownership.owners.length
  const shareLabel = n === 2 ? '½' : `1/${n}`
  return (
    <div className="rounded-2xl border border-edge bg-surface p-5">
      <h2 className="text-base font-medium">Eigendomsverdeling</h2>

      {totalEquity > 0 && (
        <div className="mt-3 flex h-2 w-full overflow-hidden rounded-full">
          {ownership.owners.map((o, i) => (
            <div
              key={o.context_id}
              style={{
                width: `${(o.equity_incl_surplus_cents / totalEquity) * 100}%`,
                backgroundColor: seriesColor(i),
              }}
            />
          ))}
        </div>
      )}

      <div className="mt-3 space-y-3 text-sm">
        {ownership.owners.map((o, i) => {
          const sharePart = o.equity_incl_surplus_cents - o.contribution_cents
          const pctOfTotal = totalEquity > 0 ? (o.equity_incl_surplus_cents / totalEquity) * 100 : 0
          return (
            <div key={o.context_id} className="rounded-xl border border-line p-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="inline-block size-2 rounded-full"
                    style={{ backgroundColor: seriesColor(i) }}
                  />
                  <span className="text-ink-2">{o.name}</span>
                </span>
                <span className="tabular-nums">
                  <span className="font-medium">{formatCents(o.equity_incl_surplus_cents)}</span>
                  <span className="ml-2 text-xs text-ink-3">{pct1.format(pctOfTotal)} %</span>
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-3">
                inbreng {formatCents(o.contribution_cents)} + {shareLabel} · (afgelost +
                meerwaarde) {formatCents(sharePart)}
              </p>
            </div>
          )
        })}
        {ownership.our_share_pct !== null && (
          <div className="flex justify-between border-t border-line pt-2">
            <span className="text-ink-2">Aandeel van ons (excl. meerwaarde)</span>
            <span className="tabular-nums font-medium">
              {pct1.format(ownership.our_share_pct * 100)} %
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function ScheduleTable({ rows }: { rows: LoanScheduleRow[] }) {
  const [open, setOpen] = useState(false)
  const paidCount = rows.filter((r) => r.paid).length
  return (
    <section className="rounded-2xl border border-edge bg-surface">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <span className="text-base font-medium">Aflossingstabel</span>
        <span className="text-sm text-ink-3">
          {paidCount}/{rows.length} betaald · {open ? 'verbergen' : 'tonen'}
        </span>
      </button>
      {open && (
        <div className="max-h-[28rem] overflow-auto border-t border-line">
          <table className="w-full min-w-[560px] text-sm tabular-nums">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-line text-xs text-ink-3">
                <th className="px-3 py-2 text-left font-medium">Datum</th>
                <th className="px-3 py-2 text-right font-medium">Maandlast</th>
                <th className="px-3 py-2 text-right font-medium">Interest</th>
                <th className="px-3 py-2 text-right font-medium">Kapitaal</th>
                <th className="px-5 py-2 text-right font-medium">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.n}
                  className={`border-b border-line last:border-b-0 ${r.paid ? '' : 'text-ink-3'}`}
                >
                  <td className="whitespace-nowrap px-3 py-1.5">{formatDate(r.date)}</td>
                  <td className="px-3 py-1.5 text-right">{formatCentsPlain(r.payment_cents)}</td>
                  <td className="px-3 py-1.5 text-right">{formatCentsPlain(r.interest_cents)}</td>
                  <td className="px-3 py-1.5 text-right">{formatCentsPlain(r.principal_cents)}</td>
                  <td className="px-5 py-1.5 text-right">{formatCentsPlain(r.balance_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// --- Bewerken ---

interface InvestmentDraft {
  label: string
  comment: string
  value: string
}

function LoanForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial: LoanOverview | null
  onSaved: (data: LoanOverview) => void
  onCancel: () => void
}) {
  const { contexts } = useAppState()
  const loan = initial?.loan
  const [name, setName] = useState(loan?.name ?? 'Woonlening')
  const [principal, setPrincipal] = useState(euro(loan?.principal_cents))
  const [ratePct, setRatePct] = useState(loan ? rateToPct(loan.annual_rate) : '')
  const [termYears, setTermYears] = useState(loan ? String(loan.term_months / 12) : '')
  const [startDate, setStartDate] = useState(loan?.start_date ?? todayIso())
  const [manualPayment, setManualPayment] = useState(euro(loan?.monthly_payment_cents ?? null))
  const [pricePaid, setPricePaid] = useState(euro(loan?.property_value_paid_cents ?? null))
  const [baseValue, setBaseValue] = useState(euro(loan?.property_base_value_cents ?? null))
  const [baseYear, setBaseYear] = useState(loan?.property_base_year ? String(loan.property_base_year) : '')
  const [indexPct, setIndexPct] = useState(loan?.indexation_rate ? rateToPct(loan.indexation_rate) : '')
  const [investments, setInvestments] = useState<InvestmentDraft[]>(
    loan?.investments.map((i) => ({
      label: i.label,
      comment: i.comment ?? '',
      value: euro(i.added_value_cents),
    })) ?? [],
  )
  const [contribs, setContribs] = useState<Record<number, string>>(() => {
    const map: Record<number, string> = {}
    loan?.contributions.forEach((c) => {
      map[c.context_id] = euro(c.amount_cents)
    })
    return map
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const rate = pctToRate(ratePct)
    const principalCents = parseEuroToCents(principal)
    const years = Number(termYears.replace(',', '.'))
    if (rate === null || principalCents === null || !Number.isInteger(years) || years <= 0) {
      setError('Bedrag, rente en looptijd (in hele jaren) zijn verplicht en geldig.')
      return
    }
    const invPayload: LoanInvestmentPayload[] = []
    for (const inv of investments) {
      const cents = parseEuroToCents(inv.value)
      if (inv.label.trim() === '' || cents === null) {
        setError('Elke investering heeft een naam en een geldig bedrag nodig.')
        return
      }
      invPayload.push({
        label: inv.label.trim(),
        comment: inv.comment.trim() === '' ? null : inv.comment.trim(),
        added_value_cents: cents,
      })
    }
    const contribPayload: LoanContributionPayload[] = []
    for (const [id, value] of Object.entries(contribs)) {
      if (value.trim() === '') continue
      const cents = parseEuroToCents(value)
      if (cents === null) {
        setError('Een inbreng-bedrag is ongeldig.')
        return
      }
      if (cents !== 0) contribPayload.push({ context_id: Number(id), amount_cents: cents })
    }

    const manualCents = manualPayment.trim() === '' ? null : parseEuroToCents(manualPayment)
    const priceCents = pricePaid.trim() === '' ? null : parseEuroToCents(pricePaid)
    const baseCents = baseValue.trim() === '' ? null : parseEuroToCents(baseValue)
    const index = indexPct.trim() === '' ? null : pctToRate(indexPct)

    const payload: LoanPayload = {
      name: name.trim() || 'Woonlening',
      principal_cents: principalCents,
      annual_rate: rate,
      term_months: years * 12,
      start_date: startDate,
      monthly_payment_cents: manualCents,
      property_value_paid_cents: priceCents,
      property_base_value_cents: baseCents,
      property_base_year: baseYear.trim() === '' ? null : Number(baseYear),
      indexation_rate: index,
      investments: invPayload,
      contributions: contribPayload,
    }
    setError(null)
    setBusy(true)
    try {
      const data = await api<LoanOverview>('/api/loan', {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      onSaved(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-10"
      onClick={onCancel}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-2xl space-y-5 rounded-2xl border border-edge bg-surface p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-medium">Lening &amp; woning bewerken</h3>

        <fieldset className="space-y-3">
          <legend className="text-xs uppercase tracking-wide text-ink-3">Lening</legend>
          <Field label="Naam">
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Bedrag (€)">
              <input className={inputClass} value={principal} onChange={(e) => setPrincipal(e.target.value)} placeholder="245.000" />
            </Field>
            <Field label="Looptijd (jaar)">
              <input className={inputClass} value={termYears} onChange={(e) => setTermYears(e.target.value)} placeholder="15" />
            </Field>
            <Field label="Nettorente (%)">
              <input className={inputClass} value={ratePct} onChange={(e) => setRatePct(e.target.value)} placeholder="2,51" />
            </Field>
            <Field label="Startdatum (1e aflossing)">
              <input type="date" className={inputClass} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="Maandlast (€) — leeg = berekend">
              <input className={inputClass} value={manualPayment} onChange={(e) => setManualPayment(e.target.value)} placeholder="1.631,52" />
            </Field>
          </div>
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-xs uppercase tracking-wide text-ink-3">Woning</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Betaalde prijs incl. kosten (€)">
              <input className={inputClass} value={pricePaid} onChange={(e) => setPricePaid(e.target.value)} placeholder="400.600" />
            </Field>
            <Field label="Basiswaarde woning (€)">
              <input className={inputClass} value={baseValue} onChange={(e) => setBaseValue(e.target.value)} placeholder="380.000" />
            </Field>
            <Field label="Basisjaar">
              <input className={inputClass} value={baseYear} onChange={(e) => setBaseYear(e.target.value)} placeholder="2024" />
            </Field>
            <Field label="Indexatie/jaar (%)">
              <input className={inputClass} value={indexPct} onChange={(e) => setIndexPct(e.target.value)} placeholder="1,5" />
            </Field>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-ink-3">Investeringen (meerwaarde)</span>
              <button
                type="button"
                onClick={() => setInvestments((v) => [...v, { label: '', comment: '', value: '' }])}
                className="text-xs text-accent hover:underline"
              >
                + toevoegen
              </button>
            </div>
            <div className="space-y-3">
              {investments.map((inv, i) => (
                <div key={i} className="space-y-1.5 rounded-xl border border-line p-2.5">
                  <div className="flex gap-2">
                    <input
                      className={`${inputClass} flex-1`}
                      placeholder="bv. Keuken"
                      value={inv.label}
                      onChange={(e) =>
                        setInvestments((v) => v.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))
                      }
                    />
                    <input
                      className={`${inputClass} w-32 text-right`}
                      placeholder="€"
                      value={inv.value}
                      onChange={(e) =>
                        setInvestments((v) => v.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))
                      }
                    />
                    <button
                      type="button"
                      onClick={() => setInvestments((v) => v.filter((_, j) => j !== i))}
                      aria-label="Verwijderen"
                      className="px-2 text-ink-3 hover:text-crit"
                    >
                      ×
                    </button>
                  </div>
                  <input
                    className={inputClass}
                    placeholder="Toelichting — bv. 50% van de aankoopprijs van de keuken (optioneel)"
                    value={inv.comment}
                    onChange={(e) =>
                      setInvestments((v) => v.map((x, j) => (j === i ? { ...x, comment: e.target.value } : x)))
                    }
                  />
                </div>
              ))}
              {investments.length === 0 && <p className="text-xs text-ink-3">Nog geen investeringen.</p>}
            </div>
          </div>

          <div>
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Eigen inbreng per persoon</span>
            <div className="space-y-2">
              {contexts.map((c) => (
                <div key={c.id} className="flex items-center gap-2">
                  <span className="flex-1 text-sm text-ink-2">{c.name}</span>
                  <input
                    className={`${inputClass} w-40 text-right`}
                    placeholder="€ 0"
                    value={contribs[c.id] ?? ''}
                    onChange={(e) => setContribs((m) => ({ ...m, [c.id]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
          </div>
        </fieldset>

        {error && <p className="text-sm text-crit">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
          >
            Opslaan
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 hover:bg-raised"
          >
            Annuleren
          </button>
        </div>
      </form>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">{label}</span>
      {children}
    </label>
  )
}

/** Centen → bewerkbare euro-string, of leeg. */
function euro(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return ''
  return formatCentsPlain(cents)
}
