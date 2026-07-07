import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, apiUpload, ApiError } from '../api/client'
import type {
  Category,
  CategoryType,
  Categorization,
  CommitRow,
  ImportCommit,
  ImportPreview,
  ImportResult,
  MatchField,
  MatchType,
  PreviewRow,
  Rule,
  RulePayload,
} from '../api/types'
import CategoryPicker from '../components/CategoryPicker'
import { formatCentsPlain, formatDate, parseEuroToCents } from '../lib/format'
import { FIELD_LABEL, MATCH_FIELDS, MATCH_TYPES, ruleMatches, TYPE_LABEL } from '../lib/rules'

const selectClass =
  'w-full rounded-lg border border-edge bg-page px-2 py-1.5 text-sm focus:border-accent focus:outline-none'
const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'

// Bewerkbare kopie van een previewrij: categorie/type/bedrag/omschrijving kunnen
// aangepast worden vóór het opslaan. `edited` = categorie manueel gekozen;
// `ruleApplied` = door een regel (server-preview of tijdens de import aangemaakt)
// gezet. `import_hash` blijft de originele dedupe-sleutel — bewerken verandert de
// identiteit van de rij niet, enkel de opgeslagen waarde.
interface EditRow {
  source: PreviewRow
  categoryId: number | null
  type: CategoryType
  edited: boolean
  ruleApplied: boolean
  amountCents: number // signed, gecommit
  amountText: string // wat in het invoerveld staat
  amountInvalid: boolean
  description: string
}

function signType(amountCents: number): CategoryType {
  return amountCents > 0 ? 'Inkomen' : 'Uitgaven'
}

function toEditRow(row: PreviewRow): EditRow {
  return {
    source: row,
    categoryId: row.suggested_category_id,
    type: row.type,
    edited: false,
    ruleApplied: row.matched_rule_id !== null,
    amountCents: row.amount_cents,
    amountText: formatCentsPlain(row.amount_cents),
    amountInvalid: false,
    description: row.description ?? '',
  }
}

function categorizationFor(row: EditRow): Categorization {
  if (row.categoryId === null) return 'uncategorized'
  if (row.edited) return 'manual'
  return row.ruleApplied ? 'auto' : 'manual'
}

// Prefill voor de regel-editor, afgeleid van een previewrij.
interface RuleDraft {
  field: MatchField
  type: MatchType
  value: string
  categoryId: number | ''
}

export default function Import() {
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [rows, setRows] = useState<EditRow[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [uploading, setUploading] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [draft, setDraft] = useState<RuleDraft>({
    field: 'counterparty_name',
    type: 'contains',
    value: '',
    categoryId: '',
  })
  const [ruleSaving, setRuleSaving] = useState(false)
  const [ruleMsg, setRuleMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const editorRef = useRef<HTMLElement>(null)
  const ruleValueRef = useRef<HTMLInputElement>(null)

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (fileRef.current) fileRef.current.value = '' // zelfde bestand opnieuw kiesbaar
    if (!file) return
    setError(null)
    setResult(null)
    setPreview(null)
    setRows([])
    setCategories([])
    setRuleMsg(null)
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const data = await apiUpload<ImportPreview>('/api/imports/preview', formData)
      setPreview(data)
      setRows(data.rows.map(toEditRow))
      if (data.account) {
        api<Category[]>(`/api/categories?context_id=${data.account.context_id}`)
          .then(setCategories)
          .catch(() => setCategories([]))
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Upload mislukt — is dit een KBC- of Fortis-CSV?',
      )
    } finally {
      setUploading(false)
    }
  }

  function changeCategory(index: number, categoryId: number | null) {
    setRows((prev) =>
      prev.map((row, i) => {
        if (i !== index) return row
        const category = categoryId === null ? null : categories.find((c) => c.id === categoryId)
        return {
          ...row,
          categoryId: category ? category.id : null,
          // met categorie volgt het type de categorie, anders het teken van het bedrag
          type: category ? category.type : signType(row.amountCents),
          edited: true,
          ruleApplied: false,
        }
      }),
    )
  }

  function changeAmount(index: number, text: string) {
    setRows((prev) =>
      prev.map((row, i) => {
        if (i !== index) return row
        const cents = parseEuroToCents(text)
        if (cents === null || cents === 0) {
          return { ...row, amountText: text, amountInvalid: true }
        }
        // Zonder categorie volgt het type het teken (zoals de backend _sign_type).
        const type = row.categoryId === null ? signType(cents) : row.type
        return { ...row, amountText: text, amountCents: cents, amountInvalid: false, type }
      }),
    )
  }

  function changeDescription(index: number, text: string) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, description: text } : row)))
  }

  // "＋ regel" op een rij: de editor voorinvullen en ernaartoe scrollen.
  function prefillRule(row: EditRow) {
    const hasName = !!row.source.counterparty_name
    setDraft({
      field: hasName ? 'counterparty_name' : 'description',
      type: 'contains',
      value: (hasName ? row.source.counterparty_name : row.description) ?? '',
      categoryId: row.categoryId ?? '',
    })
    setRuleMsg(null)
    editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // focus ná het scrollen zodat de gebruiker de waarde meteen kan bijwerken
    setTimeout(() => ruleValueRef.current?.select(), 150)
  }

  // Client-side dezelfde regel toepassen op de preview (rijen die de gebruiker
  // niet zelf aanpaste), zodat de match meteen zichtbaar is.
  function applyRuleToPreview(rule: Rule, category: Category): number {
    let updated = 0
    setRows((prev) =>
      prev.map((row) => {
        if (row.edited || row.source.duplicate || row.source.is_internal_transfer) return row
        const candidate = {
          counterparty_name: row.source.counterparty_name,
          counterparty_iban: row.source.counterparty_iban,
          description: row.description,
        }
        if (!ruleMatches(candidate, rule)) return row
        updated += 1
        return { ...row, categoryId: category.id, type: category.type, ruleApplied: true }
      }),
    )
    return updated
  }

  async function saveRule(e: FormEvent) {
    e.preventDefault()
    if (!preview?.account) return
    if (draft.value.trim() === '' || draft.categoryId === '') {
      setRuleMsg('Waarde en categorie zijn verplicht')
      return
    }
    setRuleSaving(true)
    setRuleMsg(null)
    const payload: RulePayload = {
      context_id: preview.account.context_id,
      match_field: draft.field,
      match_type: draft.type,
      match_value: draft.value.trim(),
      category_id: draft.categoryId,
      priority: 100,
      created_from_correction: false,
    }
    try {
      const rule = await api<Rule>('/api/rules', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      const category = categories.find((c) => c.id === rule.category_id)
      const updated = category ? applyRuleToPreview(rule, category) : 0
      setDraft((d) => ({ ...d, value: '' }))
      setRuleMsg(
        `Regel opgeslagen — ${updated} rij${updated === 1 ? '' : 'en'} in dit voorbeeld bijgewerkt.`,
      )
    } catch (err) {
      setRuleMsg(err instanceof ApiError ? err.message : 'Regel opslaan mislukt — probeer opnieuw')
    } finally {
      setRuleSaving(false)
    }
  }

  async function commit() {
    if (!preview?.account) return
    setError(null)
    setCommitting(true)
    const commitRows: CommitRow[] = rows
      .filter((row) => !row.source.duplicate)
      .map((row) => ({
        date: row.source.date,
        effective_date: row.source.effective_date,
        amount_cents: row.amountCents,
        type: row.type,
        counterparty_name: row.source.counterparty_name,
        counterparty_iban: row.source.counterparty_iban,
        description: row.description.trim() || null,
        import_hash: row.source.import_hash,
        category_id: row.source.is_internal_transfer ? null : row.categoryId,
        categorization: categorizationFor(row),
        is_internal_transfer: row.source.is_internal_transfer,
      }))
    const body: ImportCommit = {
      filename: preview.filename,
      bank: preview.bank,
      account_id: preview.account.id,
      context_id: preview.account.context_id,
      rows: commitRows,
    }
    try {
      const res = await api<ImportResult>('/api/imports/commit', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      setResult(res)
      setPreview(null)
      setRows([])
      setRuleMsg(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt — probeer opnieuw')
    } finally {
      setCommitting(false)
    }
  }

  const newRows = rows.filter((r) => !r.source.duplicate).length
  const invalidRows = rows.filter((r) => !r.source.duplicate && r.amountInvalid).length

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Bankafschriften importeren</h1>

      <section className="rounded-2xl border border-edge bg-surface p-5">
        <p className="text-sm text-ink-2">
          Laad een CSV-export van KBC of BNP Paribas Fortis op. Je krijgt eerst een
          voorbeeld met voorgestelde categorieën; niets wordt opgeslagen voor je bevestigt.
        </p>
        <label className="mt-3 inline-flex cursor-pointer items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={onFile}
            className="hidden"
          />
          {uploading ? 'Bezig met inlezen…' : 'CSV kiezen'}
        </label>
      </section>

      {error && (
        <div className="rounded-2xl border border-crit/40 bg-surface p-4 text-sm text-crit">
          {error}
        </div>
      )}

      {result && (
        <div className="rounded-2xl border border-good/40 bg-surface p-5 text-sm">
          <p className="font-medium text-good">Import geslaagd</p>
          <p className="mt-1 text-ink-2">
            {result.created_count} nieuwe transactie{result.created_count === 1 ? '' : 's'}{' '}
            toegevoegd
            {result.duplicate_count > 0 &&
              `, ${result.duplicate_count} duplicaat${
                result.duplicate_count === 1 ? '' : 'en'
              } overgeslagen`}
            .
          </p>
        </div>
      )}

      {preview && (
        <>
          <PreviewSummary preview={preview} newRows={newRows} />

          {preview.account ? (
            <>
              <RuleEditor
                ref={editorRef}
                valueRef={ruleValueRef}
                draft={draft}
                setDraft={setDraft}
                categories={categories}
                saving={ruleSaving}
                message={ruleMsg}
                onSubmit={saveRule}
              />

              <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
                <PreviewTable
                  rows={rows}
                  categories={categories}
                  onChangeCategory={changeCategory}
                  onChangeAmount={changeAmount}
                  onChangeDescription={changeDescription}
                  onAddRule={prefillRule}
                />
                <div className="flex items-center gap-3 border-t border-line px-5 py-3">
                  <button
                    onClick={() => void commit()}
                    disabled={committing || newRows === 0 || invalidRows > 0}
                    className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
                  >
                    {committing
                      ? 'Bezig met opslaan…'
                      : `Bevestigen en ${newRows} transactie${
                          newRows === 1 ? '' : 's'
                        } opslaan`}
                  </button>
                  {invalidRows > 0 ? (
                    <span className="text-sm text-crit">
                      {invalidRows} rij(en) met een ongeldig bedrag — corrigeer voor je opslaat.
                    </span>
                  ) : (
                    newRows === 0 && (
                      <span className="text-sm text-ink-3">
                        Alle rijen zijn duplicaten — niets te importeren.
                      </span>
                    )
                  )}
                </div>
              </section>
            </>
          ) : (
            <div className="rounded-2xl border border-warn/40 bg-surface p-5 text-sm text-ink-2">
              De rekening uit dit bestand is niet gekend
              {preview.unmatched_ibans.length > 0 &&
                ` (${preview.unmatched_ibans.join(', ')})`}
              . Voeg de rekening toe met dit IBAN voor je kan importeren.
            </div>
          )}
        </>
      )}
    </div>
  )
}

function PreviewSummary({ preview, newRows }: { preview: ImportPreview; newRows: number }) {
  return (
    <section className="rounded-2xl border border-edge bg-surface p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="rounded-md bg-raised px-2 py-0.5 text-xs font-medium text-ink-2">
          {preview.bank}
        </span>
        <span className="text-sm font-medium">{preview.filename}</span>
        {preview.account && (
          <span className="text-sm text-ink-3">
            → {preview.account.name} ({preview.account.context_name})
          </span>
        )}
      </div>
      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm tabular-nums">
        <div>
          <dt className="inline text-ink-3">Nieuw: </dt>
          <dd className="inline font-medium">{newRows}</dd>
        </div>
        <div>
          <dt className="inline text-ink-3">Duplicaten: </dt>
          <dd className="inline font-medium">{preview.duplicate_count}</dd>
        </div>
        <div>
          <dt className="inline text-ink-3">Zonder categorie: </dt>
          <dd className="inline font-medium">{preview.uncategorized_count}</dd>
        </div>
      </dl>
      {preview.skipped.length > 0 && (
        <p className="mt-3 text-xs text-ink-3">
          {preview.skipped.length} rij(en) overgeslagen (geweigerd/niet-geaccepteerd).
        </p>
      )}
    </section>
  )
}

function RuleEditor({
  ref,
  valueRef,
  draft,
  setDraft,
  categories,
  saving,
  message,
  onSubmit,
}: {
  ref: React.RefObject<HTMLElement | null>
  valueRef: React.RefObject<HTMLInputElement | null>
  draft: RuleDraft
  setDraft: React.Dispatch<React.SetStateAction<RuleDraft>>
  categories: Category[]
  saving: boolean
  message: string | null
  onSubmit: (e: FormEvent) => void
}) {
  return (
    <section ref={ref} className="rounded-2xl border border-edge bg-surface p-5">
      <h2 className="text-sm font-medium">Regel toevoegen tijdens de import</h2>
      <p className="mt-1 text-xs text-ink-3">
        Maak een regel op basis van een rij hieronder (knop “＋ regel”) of vul ze zelf in.
        De regel wordt bewaard en meteen op dit voorbeeld toegepast.
      </p>
      <form onSubmit={onSubmit} className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Veld</span>
          <select
            value={draft.field}
            onChange={(e) => setDraft((d) => ({ ...d, field: e.target.value as MatchField }))}
            className={inputClass}
          >
            {MATCH_FIELDS.map((f) => (
              <option key={f} value={f}>
                {FIELD_LABEL[f]}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Match</span>
          <select
            value={draft.type}
            onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value as MatchType }))}
            className={inputClass}
          >
            {MATCH_TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </label>
        <label className="block lg:col-span-2">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Waarde</span>
          <input
            ref={valueRef}
            type="text"
            value={draft.value}
            onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))}
            placeholder={draft.type === 'regex' ? 'bv. mobile\\s+vikings' : 'bv. COLRUYT'}
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Categorie</span>
          <CategoryPicker
            categories={categories}
            value={draft.categoryId === '' ? null : draft.categoryId}
            onChange={(id) => setDraft((d) => ({ ...d, categoryId: id ?? '' }))}
            groupByType
            placeholder="— kies —"
            ariaLabel="Categorie"
            className={inputClass}
          />
        </label>
        <div className="flex items-center gap-3 sm:col-span-2 lg:col-span-6">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
          >
            {saving ? 'Bezig…' : 'Regel opslaan'}
          </button>
          {message && <p className="text-sm text-ink-2">{message}</p>}
        </div>
      </form>
    </section>
  )
}

function PreviewTable({
  rows,
  categories,
  onChangeCategory,
  onChangeAmount,
  onChangeDescription,
  onAddRule,
}: {
  rows: EditRow[]
  categories: Category[]
  onChangeCategory: (index: number, categoryId: number | null) => void
  onChangeAmount: (index: number, text: string) => void
  onChangeDescription: (index: number, text: string) => void
  onAddRule: (row: EditRow) => void
}) {
  return (
    <table className="w-full min-w-[1000px] text-sm">
      <thead>
        <tr className="border-b border-line text-xs text-ink-3">
          <th className="px-5 py-3 text-left font-medium">Datum</th>
          <th className="px-3 py-3 text-left font-medium">Tegenpartij</th>
          <th className="px-3 py-3 text-left font-medium">Omschrijving</th>
          <th className="px-3 py-3 text-right font-medium">Bedrag</th>
          <th className="px-3 py-3 text-left font-medium">Categorie</th>
        </tr>
      </thead>
      <tbody className="tabular-nums">
        {rows.map((row, index) => {
          const dupe = row.source.duplicate
          return (
            <tr
              key={row.source.import_hash}
              className={`border-b border-line last:border-b-0 ${
                dupe ? 'opacity-45' : 'hover:bg-raised/50'
              }`}
            >
              <td className="whitespace-nowrap px-5 py-2">{formatDate(row.source.date)}</td>
              <td className="max-w-48 truncate px-3 py-2">
                {row.source.counterparty_name ?? (
                  <span className="text-ink-3">–</span>
                )}
              </td>
              <td className="px-3 py-2 text-ink-2">
                {dupe ? (
                  <span className="block max-w-64 truncate">{row.source.description ?? ''}</span>
                ) : (
                  <input
                    type="text"
                    value={row.description}
                    onChange={(e) => onChangeDescription(index, e.target.value)}
                    aria-label="Omschrijving"
                    className="w-full min-w-[12rem] rounded-lg border border-edge bg-page px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
                  />
                )}
              </td>
              <td className="px-3 py-2 text-right">
                {dupe ? (
                  formatCentsPlain(row.source.amount_cents)
                ) : (
                  <input
                    type="text"
                    inputMode="decimal"
                    value={row.amountText}
                    onChange={(e) => onChangeAmount(index, e.target.value)}
                    aria-label="Bedrag"
                    aria-invalid={row.amountInvalid}
                    className={`w-28 rounded-lg border border-edge bg-page px-2 py-1.5 text-right text-sm tabular-nums focus:border-accent focus:outline-none ${
                      row.amountInvalid ? 'border-crit' : ''
                    }`}
                  />
                )}
              </td>
              <td className="px-3 py-2">
                {dupe ? (
                  <span className="text-xs text-ink-3">duplicaat</span>
                ) : row.source.is_internal_transfer ? (
                  <span className="text-xs text-ink-3">interne overschrijving</span>
                ) : (
                  <div className="flex items-center gap-2">
                    <CategoryPicker
                      categories={categories}
                      value={row.categoryId}
                      onChange={(id) => onChangeCategory(index, id)}
                      groupByType
                      allowEmpty
                      emptyLabel="— ongecategoriseerd —"
                      placeholder="— ongecategoriseerd —"
                      ariaLabel="Categorie"
                      className={selectClass}
                      wrapperClassName="flex-1"
                    />
                    <button
                      type="button"
                      onClick={() => onAddRule(row)}
                      title="Maak een regel op basis van deze rij"
                      className="whitespace-nowrap rounded-lg border border-edge bg-surface px-2 py-1.5 text-xs text-ink-2 transition-colors hover:bg-raised"
                    >
                      ＋ regel
                    </button>
                  </div>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
