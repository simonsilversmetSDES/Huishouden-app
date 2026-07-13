import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { api, ApiError } from '../api/client'
import type {
  AssetClass,
  ForecastFormulaPayload,
  ForecastMatrix,
  ForecastNotePayload,
  ForecastRow,
} from '../api/types'
import { ASSET_CLASS_LABEL } from '../lib/chartColors'
import { formatCentsWhole, formatMonthYear, MAAND_KORT } from '../lib/format'
import { useCoarsePointer } from '../lib/useMediaQuery'
import { NoteMarker, useCellNotes } from './cellNotes'

/** Vermogensforecast ("Status balans" uit de Excel): balans per activaklasse,
 * werkelijke maanden + doorgerekende formules, onder de budgetmatrix. */
export default function ForecastTable({
  contextId,
  year,
  refreshKey,
}: {
  contextId: number | null
  year: number
  refreshKey: number
}) {
  const [matrix, setMatrix] = useState<ForecastMatrix | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Selectie: een rijlabel (month=null → rij-formule) of één cel (→ override).
  const [selection, setSelection] = useState<{ assetClass: AssetClass; month: number | null } | null>(null)
  const [editText, setEditText] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const coarse = useCoarsePointer() // touch: geen vulgreepje (sleep = scrollen)

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    api<ForecastMatrix>(`/api/forecast?context_id=${contextId}&year=${year}`)
      .then(setMatrix)
      .catch(() => setError('Forecast laden mislukt — probeer opnieuw'))
  }, [contextId, year])

  useEffect(load, [load, refreshKey])

  const rowByClass = useMemo(
    () => new Map((matrix?.rows ?? []).map((r) => [r.asset_class, r])),
    [matrix],
  )

  // Celnotities (Excel-achtig): zelfde gedrag als de budgetmatrix; sleutel "klasse:maand".
  const notes = useCellNotes({
    noteFor: (key) => {
      const [assetClass, m] = key.split(':')
      return rowByClass.get(assetClass as AssetClass)?.cells[Number(m) - 1]?.note ?? null
    },
    onSave: async (key, note) => {
      if (contextId === null) return
      const [assetClass, m] = key.split(':')
      await api<void>('/api/forecast/notes', {
        method: 'PUT',
        body: JSON.stringify({
          context_id: contextId,
          asset_class: assetClass as AssetClass,
          year,
          month: Number(m),
          note,
        } satisfies ForecastNotePayload),
      })
      load()
    },
    // Rechtsklik selecteert de cel, zodat de formulebalk meteen meekijkt.
    onMenuOpen: (key) => {
      const [assetClass, m] = key.split(':')
      select(assetClass as AssetClass, Number(m))
    },
  })

  // Doortrekken (Excel-vulgreepje): sleep de formule van een forecastcel als
  // override naar andere maanden in dezelfde rij; werkelijke maanden slaan we over.
  const [fillPreview, setFillPreview] = useState<Set<number> | null>(null)
  const fillingRef = useRef(false)
  const fillSourceRef = useRef<{ assetClass: AssetClass; month: number; formula: string } | null>(null)
  const fillTargetsRef = useRef<number[]>([])

  /** Doelmaanden tussen bron en muispositie (bron zelf uitgezonderd), enkel cellen
   * die geen werkelijke maand zijn. */
  const fillTargetMonths = useCallback(
    (row: ForecastRow, source: number, hover: number): number[] => {
      const [from, to] = hover > source ? [source + 1, hover] : [hover, source - 1]
      const months: number[] = []
      for (let m = from; m <= to; m++) {
        if (row.cells[m - 1].kind !== 'werkelijk') months.push(m)
      }
      return months
    },
    [],
  )

  const commitFill = useCallback(async () => {
    const source = fillSourceRef.current
    const targets = fillTargetsRef.current
    fillingRef.current = false
    fillSourceRef.current = null
    fillTargetsRef.current = []
    setFillPreview(null)
    if (contextId === null || source === null || targets.length === 0) return
    setBusy(true)
    setSaveError(null)
    try {
      for (const month of targets) {
        await api<void>('/api/forecast/formulas', {
          method: 'PUT',
          body: JSON.stringify({
            context_id: contextId,
            asset_class: source.assetClass,
            year,
            month,
            formula: source.formula,
          } satisfies ForecastFormulaPayload),
        })
      }
      load()
    } catch (err) {
      setSaveError(
        err instanceof ApiError ? err.message : 'Doortrekken mislukt — probeer opnieuw',
      )
    } finally {
      setBusy(false)
    }
  }, [contextId, year, load])

  useEffect(() => {
    function onUp() {
      if (fillingRef.current) void commitFill()
    }
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape' && fillingRef.current) {
        fillingRef.current = false
        fillSourceRef.current = null
        fillTargetsRef.current = []
        setFillPreview(null)
      }
    }
    window.addEventListener('mouseup', onUp)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mouseup', onUp)
      window.removeEventListener('keydown', onKey)
    }
  }, [commitFill])

  const selectedRow: ForecastRow | null =
    selection !== null ? (rowByClass.get(selection.assetClass) ?? null) : null
  const selectedCell =
    selection !== null && selection.month !== null && selectedRow !== null
      ? selectedRow.cells[selection.month - 1]
      : null
  // Werkelijke maanden zijn geen forecast: formule daar niet bewerkbaar (v1).
  const editable = selectedRow !== null && (selectedCell === null || selectedCell.kind !== 'werkelijk')

  function effectiveFormula(row: ForecastRow, month: number | null): string {
    if (month !== null) {
      const cell = row.cells[month - 1]
      if (cell.override_formula !== null) return cell.override_formula
    }
    return row.formula
  }

  function select(assetClass: AssetClass, month: number | null) {
    const row = rowByClass.get(assetClass)
    if (row === undefined) return
    setSelection({ assetClass, month })
    setEditText(effectiveFormula(row, month))
    setSaveError(null)
  }

  function onFillHandleMouseDown(e: React.MouseEvent) {
    // Niet doorgeven aan de cel: het greepje start doortrekken, geen nieuwe selectie.
    e.preventDefault()
    e.stopPropagation()
    if (selection === null || selection.month === null || busy) return
    const row = rowByClass.get(selection.assetClass)
    if (row === undefined) return
    fillingRef.current = true
    fillSourceRef.current = {
      assetClass: selection.assetClass,
      month: selection.month,
      formula: effectiveFormula(row, selection.month),
    }
    fillTargetsRef.current = []
    setFillPreview(new Set())
  }

  function onCellFillHover(row: ForecastRow, month: number) {
    const source = fillSourceRef.current
    if (!fillingRef.current || source === null || row.asset_class !== source.assetClass) return
    const targets = fillTargetMonths(row, source.month, month)
    fillTargetsRef.current = targets
    setFillPreview(new Set(targets))
  }

  const put = useCallback(
    async (payload: ForecastFormulaPayload) => {
      setBusy(true)
      setSaveError(null)
      try {
        await api<void>('/api/forecast/formulas', {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
        load()
      } catch (err) {
        setSaveError(
          err instanceof ApiError ? err.message : 'Formule opslaan mislukt — probeer opnieuw',
        )
      } finally {
        setBusy(false)
      }
    },
    [load],
  )

  function save() {
    if (contextId === null || selection === null || !editable) return
    void put({
      context_id: contextId,
      asset_class: selection.assetClass,
      year: selection.month === null ? null : year,
      month: selection.month,
      formula: editText,
    })
  }

  function resetToDefault() {
    if (contextId === null || selection === null) return
    void put({
      context_id: contextId,
      asset_class: selection.assetClass,
      year: selection.month === null ? null : year,
      month: selection.month,
      formula: '',
    })
  }

  function onEditKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      save()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      if (selectedRow !== null && selection !== null) {
        setEditText(effectiveFormula(selectedRow, selection.month))
      }
      setSaveError(null)
    }
  }

  if (contextId === null) return null
  if (error) {
    return (
      <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
        {error}{' '}
        <button onClick={load} className="text-accent hover:underline">
          Opnieuw
        </button>
      </div>
    )
  }
  if (!matrix) return null

  const lastActual = matrix.last_actual_month
  const showReset =
    selection !== null &&
    (selection.month !== null
      ? (selectedCell?.override ?? false)
      : selectedRow !== null && !selectedRow.is_default)

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h2 className="text-base font-medium">Vermogensforecast</h2>
        <span className="text-xs text-ink-3">
          {lastActual
            ? `werkelijk t/m ${formatMonthYear(
                Number(lastActual.slice(0, 4)),
                Number(lastActual.slice(5, 7)),
              )}, daarna doorgerekend op basis van budget en lening`
            : 'nog geen werkelijke balans — forecast start op € 0'}
        </span>
      </div>

      {/* Formulebalk (Excel-gevoel): toont en bewerkt de formule van de selectie. */}
      <div className="rounded-2xl border border-edge bg-surface px-4 py-3 text-sm">
        {selection === null || selectedRow === null ? (
          <p className="text-xs text-ink-3">
            Klik een rijnaam om de formule van die rij te bekijken of te bewerken, of een
            forecastcel voor een override in één maand; sleep het blauwe hoekje van een
            geselecteerde cel om die formule door te trekken. Beschikbaar:{' '}
            <code className="rounded bg-raised px-1">vorige</code>,{' '}
            <code className="rounded bg-raised px-1">kapitaalaflossing</code> (lening, die
            maand) en <code className="rounded bg-raised px-1">budget("Categorie")</code>{' '}
            (gepland maandbedrag uit de budgettabel).
          </p>
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {ASSET_CLASS_LABEL[selection.assetClass]}
                {selection.month !== null && ` — ${MAAND_KORT[selection.month - 1]} ${year}`}
              </span>
              <span className="rounded-full border border-edge bg-raised px-2 py-0.5 text-[10px] text-ink-3">
                {selection.month !== null
                  ? (selectedCell?.override ? 'override' : 'rij-formule')
                  : selectedRow.is_default
                    ? 'standaard'
                    : 'aangepast'}
              </span>
              {!editable && (
                <span className="text-xs text-ink-3">
                  werkelijke maand — hier valt niets te voorspellen
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-ink-3">=</span>
              <input
                value={editText}
                disabled={busy || !editable}
                onChange={(e) => {
                  setEditText(e.target.value)
                  setSaveError(null)
                }}
                onKeyDown={onEditKeyDown}
                spellCheck={false}
                className="min-w-64 flex-1 rounded-lg border border-edge bg-raised px-3 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-60"
              />
              <button
                onClick={save}
                disabled={busy || !editable}
                className="rounded bg-accent px-2.5 py-1.5 text-xs font-medium text-white hover:bg-accent/85 disabled:opacity-50"
              >
                Opslaan
              </button>
              {showReset && (
                <button
                  onClick={resetToDefault}
                  disabled={busy}
                  className="text-xs text-ink-3 hover:text-ink-2"
                >
                  Terug naar standaard
                </button>
              )}
            </div>
            {saveError && <p className="text-xs text-crit">{saveError}</p>}
            {selectedRow.warnings.map((w) => (
              <p key={w} className="text-xs text-warn">
                ⚠ {w}
              </p>
            ))}
          </div>
        )}
      </div>

      <div className="overflow-x-auto overscroll-x-contain rounded-2xl border border-edge bg-surface">
        <table className="w-full min-w-[760px] select-none border-collapse text-sm max-md:text-xs">
          <thead>
            <tr className="text-xs text-ink-3">
              <th className="sticky-col px-4 py-3 text-left font-medium max-md:px-3">
                Balans
              </th>
              {MAAND_KORT.map((m, i) => {
                const monthDate = `${year}-${String(i + 1).padStart(2, '0')}-01`
                const isActual = lastActual !== null && monthDate <= lastActual
                return (
                  <th
                    key={m}
                    className={`px-2 py-3 text-right font-medium ${isActual ? '' : 'italic'}`}
                  >
                    {m}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {matrix.rows.map((row) => (
              <tr key={row.asset_class} className="border-t border-line">
                <td
                  onClick={() => select(row.asset_class, null)}
                  className={`sticky-col cursor-pointer px-4 py-2.5 hover:text-accent max-md:px-3 ${
                    selection?.assetClass === row.asset_class && selection.month === null
                      ? 'text-accent'
                      : ''
                  }`}
                  title="Klik om de rij-formule te bewerken"
                >
                  {ASSET_CLASS_LABEL[row.asset_class]}
                  {!row.is_default && <span className="ml-1 text-[10px] text-accent">ƒ</span>}
                  {row.warnings.length > 0 && (
                    <span className="ml-1 text-[10px] text-warn" title={row.warnings.join('\n')}>
                      ⚠
                    </span>
                  )}
                </td>
                {row.cells.map((cell, i) => {
                  const isSelected =
                    selection?.assetClass === row.asset_class && selection.month === i + 1
                  const inFillPreview =
                    selection?.assetClass === row.asset_class &&
                    (fillPreview?.has(i + 1) ?? false)
                  const key = `${row.asset_class}:${i + 1}`
                  return (
                    <td
                      key={i}
                      onClick={() => select(row.asset_class, i + 1)}
                      onContextMenu={(e) => notes.onContextMenu(key, e)}
                      {...notes.longPress(key)}
                      onMouseEnter={(e) => {
                        onCellFillHover(row, i + 1)
                        notes.onHoverStart(key, e)
                      }}
                      onMouseLeave={() => notes.onHoverEnd(key)}
                      title={cell.error ?? undefined}
                      className={`no-callout relative cursor-pointer px-2 py-2.5 text-right max-md:px-1.5 ${
                        isSelected
                          ? 'ring-1 ring-inset ring-accent'
                          : inFillPreview
                            ? 'bg-accent/5 ring-1 ring-inset ring-accent/50'
                            : ''
                      } ${
                        cell.kind === 'error'
                          ? 'text-crit'
                          : cell.kind === 'werkelijk'
                            ? 'bg-raised/40 text-ink-3'
                            : ''
                      }`}
                    >
                      {cell.kind === 'error'
                        ? 'fout'
                        : cell.value_cents === null
                          ? ''
                          : formatCentsWhole(cell.value_cents)}
                      {notes.hasNote(key) && <NoteMarker />}
                      {isSelected && !coarse && cell.kind !== 'werkelijk' && !busy && (
                        <span
                          onMouseDown={onFillHandleMouseDown}
                          title="Doortrekken: sleep om deze formule als override te kopiëren"
                          className="absolute -bottom-[3px] -right-[3px] z-10 size-2 cursor-crosshair border border-white bg-accent"
                        />
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
            <tr className="border-t border-line font-medium">
              <td className="sticky-col px-4 py-2.5 max-md:px-3">Totaal</td>
              {matrix.totals.map((cell, i) => (
                <td
                  key={i}
                  className={`px-2 py-2.5 text-right ${
                    cell.kind === 'error'
                      ? 'text-crit'
                      : cell.kind === 'werkelijk'
                        ? 'bg-raised/40 text-ink-3'
                        : ''
                  }`}
                >
                  {cell.kind === 'error'
                    ? 'fout'
                    : cell.value_cents === null
                      ? ''
                      : formatCentsWhole(cell.value_cents)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      {notes.overlays}
    </section>
  )
}
