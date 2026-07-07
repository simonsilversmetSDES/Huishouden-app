import { useMemo, useRef, useState, type ChangeEvent } from 'react'
import { api, apiUpload, ApiError } from '../api/client'
import type {
  Category,
  CategoryType,
  Categorization,
  CommitRow,
  ImportCommit,
  ImportPreview,
  ImportResult,
  PreviewRow,
} from '../api/types'
import { formatCentsPlain, formatDate } from '../lib/format'

const TYPES: CategoryType[] = ['Inkomen', 'Uitgaven', 'Sparen']

const selectClass =
  'w-full rounded-lg border border-edge bg-page px-2 py-1.5 text-sm focus:border-accent focus:outline-none'

// Bewerkbare kopie van een previewrij: categorie/type kunnen aangepast worden
// vóór het opslaan. `edited` bepaalt of we auto- of manueel-categorisatie sturen.
interface EditRow {
  source: PreviewRow
  categoryId: number | null
  type: CategoryType
  edited: boolean
}

function toEditRow(row: PreviewRow): EditRow {
  return {
    source: row,
    categoryId: row.suggested_category_id,
    type: row.type,
    edited: false,
  }
}

function categorizationFor(row: EditRow): Categorization {
  if (row.categoryId === null) return 'uncategorized'
  return !row.edited && row.source.matched_rule_id !== null ? 'auto' : 'manual'
}

export default function Import() {
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [rows, setRows] = useState<EditRow[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [uploading, setUploading] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const categoriesByType = useMemo(() => {
    const grouped: Record<CategoryType, Category[]> = { Inkomen: [], Uitgaven: [], Sparen: [] }
    for (const c of categories) grouped[c.type].push(c)
    return grouped
  }, [categories])

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (fileRef.current) fileRef.current.value = '' // zelfde bestand opnieuw kiesbaar
    if (!file) return
    setError(null)
    setResult(null)
    setPreview(null)
    setRows([])
    setCategories([])
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
          type: category ? category.type : row.source.type,
          edited: true,
        }
      }),
    )
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
        amount_cents: row.source.amount_cents,
        type: row.type,
        counterparty_name: row.source.counterparty_name,
        counterparty_iban: row.source.counterparty_iban,
        description: row.source.description,
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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt — probeer opnieuw')
    } finally {
      setCommitting(false)
    }
  }

  const newRows = rows.filter((r) => !r.source.duplicate).length

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
            <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
              <PreviewTable
                rows={rows}
                categoriesByType={categoriesByType}
                onChangeCategory={changeCategory}
              />
              <div className="flex items-center gap-3 border-t border-line px-5 py-3">
                <button
                  onClick={() => void commit()}
                  disabled={committing || newRows === 0}
                  className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
                >
                  {committing
                    ? 'Bezig met opslaan…'
                    : `Bevestigen en ${newRows} transactie${
                        newRows === 1 ? '' : 's'
                      } opslaan`}
                </button>
                {newRows === 0 && (
                  <span className="text-sm text-ink-3">
                    Alle rijen zijn duplicaten — niets te importeren.
                  </span>
                )}
              </div>
            </section>
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

function PreviewTable({
  rows,
  categoriesByType,
  onChangeCategory,
}: {
  rows: EditRow[]
  categoriesByType: Record<CategoryType, Category[]>
  onChangeCategory: (index: number, categoryId: number | null) => void
}) {
  return (
    <table className="w-full min-w-[820px] text-sm">
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
              <td className="max-w-64 truncate px-3 py-2 text-ink-2">
                {row.source.description ?? ''}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right">
                {formatCentsPlain(row.source.amount_cents)}
              </td>
              <td className="px-3 py-2">
                {dupe ? (
                  <span className="text-xs text-ink-3">duplicaat</span>
                ) : row.source.is_internal_transfer ? (
                  <span className="text-xs text-ink-3">interne overschrijving</span>
                ) : (
                  <select
                    value={row.categoryId ?? ''}
                    onChange={(e) =>
                      onChangeCategory(
                        index,
                        e.target.value === '' ? null : Number(e.target.value),
                      )
                    }
                    aria-label="Categorie"
                    className={selectClass}
                  >
                    <option value="">— ongecategoriseerd —</option>
                    {TYPES.map((type) => (
                      <optgroup key={type} label={type}>
                        {categoriesByType[type].map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
