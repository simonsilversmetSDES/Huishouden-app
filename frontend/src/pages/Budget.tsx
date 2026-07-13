import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'
import { api, ApiError } from '../api/client'
import type {
  BudgetCellUpdate,
  BudgetMatrix,
  BudgetNotePayload,
  Category,
  CategoryPayload,
  CategoryType,
} from '../api/types'
import ForecastTable from '../components/ForecastTable'
import { NoteMarker, useCellNotes, type CellNotes } from '../components/cellNotes'
import { formatCentsWhole, MAAND_KORT, parseEuroToCents } from '../lib/format'
import { useCoarsePointer } from '../lib/useMediaQuery'
import { useAppState } from '../state/AppState'

export default function Budget() {
  const { contextId } = useAppState()
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [matrix, setMatrix] = useState<BudgetMatrix | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [catError, setCatError] = useState<string | null>(null)
  // De forecast rekent met budgetcellen en categorieën: na elke mutatie herladen.
  const [forecastRefresh, setForecastRefresh] = useState(0)
  const bumpForecast = useCallback(() => setForecastRefresh((k) => k + 1), [])

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    api<BudgetMatrix>(`/api/budgets?context_id=${contextId}&year=${year}`)
      .then(setMatrix)
      .catch(() => setError('Budget laden mislukt — probeer opnieuw'))
  }, [contextId, year])

  useEffect(load, [load])

  const save = useCallback(
    async (items: BudgetCellUpdate[]) => {
      await api<void>('/api/budgets', {
        method: 'PUT',
        body: JSON.stringify({ items }),
      })
      load()
      bumpForecast()
    },
    [load, bumpForecast],
  )

  const saveNote = useCallback(
    async (payload: BudgetNotePayload) => {
      await api<void>('/api/budgets/notes', {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      load()
    },
    [load],
  )

  const addCategory = useCallback(
    async (type: CategoryType, name: string): Promise<boolean> => {
      if (contextId === null) return false
      setCatError(null)
      const payload: CategoryPayload = { context_id: contextId, name, type }
      try {
        await api<Category>('/api/categories', { method: 'POST', body: JSON.stringify(payload) })
        load()
        bumpForecast()
        return true
      } catch (err) {
        setCatError(
          err instanceof ApiError && err.status === 409
            ? `Categorie "${name}" bestaat al in deze context`
            : 'Categorie toevoegen mislukt — probeer opnieuw',
        )
        return false
      }
    },
    [contextId, load],
  )

  const deleteCategory = useCallback(
    async (id: number, name: string) => {
      if (
        !window.confirm(
          `Categorie "${name}" verwijderen? Ze verdwijnt uit de kiezers en de budgetmatrix; ` +
            'bestaande transacties houden hun categorie.',
        )
      ) {
        return
      }
      setCatError(null)
      try {
        await api<void>(`/api/categories/${id}`, { method: 'DELETE' })
        load()
        bumpForecast()
      } catch {
        setCatError('Categorie verwijderen mislukt — probeer opnieuw')
      }
    },
    [load, bumpForecast],
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold">Budget {year}</h1>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => setYear((y) => y - 1)}
            aria-label="Vorig jaar"
            className="rounded-lg border border-edge bg-surface px-3 py-1.5 text-sm text-ink-2 hover:bg-raised"
          >
            ‹
          </button>
          <button
            onClick={() => setYear((y) => y + 1)}
            aria-label="Volgend jaar"
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

      {catError && (
        <div className="rounded-2xl border border-crit/40 bg-surface p-4 text-sm text-crit">
          {catError}
        </div>
      )}

      {/* De matrix breekt uit de smalle paginakolom zodat de 12 maanden op een
          desktop volledig zichtbaar zijn; op smalle schermen scrolt ze horizontaal. */}
      {!error && matrix && (
        <div className="relative left-1/2 w-[94vw] max-w-[1440px] -translate-x-1/2">
          <MatrixTable
            matrix={matrix}
            year={year}
            onSave={save}
            onSaveNote={saveNote}
            onAddCategory={addCategory}
            onDeleteCategory={deleteCategory}
          />
        </div>
      )}
      {!error && !matrix && <p className="py-12 text-center text-sm text-ink-3">Laden…</p>}

      <p className="text-xs text-ink-3">
        Klik een cel om te bewerken · sleep of Shift/Ctrl-klik om meerdere cellen te
        selecteren · sleep het <strong>blauwe hoekje</strong> om waarden door te trekken
        (zoals in Excel) · typ een bedrag en <strong>Ctrl+Enter</strong> vult alle
        geselecteerde cellen · <strong>Delete</strong> wist de selectie · Enter = opslaan ·
        Esc = annuleren · rechtsklik = notitie
      </p>

      {/* Vermogensforecast ("Status balans"), in dezelfde brede kolom als de matrix. */}
      {!error && (
        <div className="relative left-1/2 w-[94vw] max-w-[1440px] -translate-x-1/2">
          <ForecastTable contextId={contextId} year={year} refreshKey={forecastRefresh} />
        </div>
      )}
    </div>
  )
}

interface MatrixTableProps {
  matrix: BudgetMatrix
  year: number
  onSave: (items: BudgetCellUpdate[]) => Promise<void>
  onSaveNote: (payload: BudgetNotePayload) => Promise<void>
  onAddCategory: (type: CategoryType, name: string) => Promise<boolean>
  onDeleteCategory: (id: number, name: string) => void
}

const cellKey = (categoryId: number, month: number) => `${categoryId}:${month}`

/** Omhullende rechthoek van een selectie, in rij-indexen en maandnummers. */
type FillRect = { r1: number; r2: number; m1: number; m2: number }

function MatrixTable({
  matrix,
  year,
  onSave,
  onSaveNote,
  onAddCategory,
  onDeleteCategory,
}: MatrixTableProps) {
  // Vlakke, geordende lijst van categorie-id's (voor rechthoekige bereikselectie) +
  // de centen en notities per cel (editor-beginwaarde, driehoekje, tooltip).
  const { orderedCats, rowIndexByCat, centsByKey, notesByKey } = useMemo(() => {
    const orderedCats: number[] = []
    const rowIndexByCat = new Map<number, number>()
    const centsByKey = new Map<string, number>()
    const notesByKey = new Map<string, string>()
    for (const group of matrix.groups) {
      for (const row of group.categories) {
        rowIndexByCat.set(row.category_id, orderedCats.length)
        orderedCats.push(row.category_id)
        row.month_cents.forEach((cents, i) =>
          centsByKey.set(cellKey(row.category_id, i + 1), cents),
        )
        row.month_notes.forEach((note, i) => {
          if (note !== null) notesByKey.set(cellKey(row.category_id, i + 1), note)
        })
      }
    }
    return { orderedCats, rowIndexByCat, centsByKey, notesByKey }
  }, [matrix])

  const coarse = useCoarsePointer() // touch: geen vulgreepje (sleep = scrollen)
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [editing, setEditing] = useState<{ categoryId: number; month: number } | null>(null)
  const [editText, setEditText] = useState('')
  const [invalid, setInvalid] = useState(false)
  const [busy, setBusy] = useState(false)

  // Refs met de laatste waarden voor de globale toets-/muishandlers (één keer geregistreerd).
  const anchorRef = useRef<{ row: number; month: number } | null>(null)
  const draggingRef = useRef(false)
  const movedRef = useRef(false)
  const skipBlurRef = useRef(false)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const editingRef = useRef(editing)
  editingRef.current = editing
  const centsRef = useRef(centsByKey)
  centsRef.current = centsByKey
  const orderedRef = useRef(orderedCats)
  orderedRef.current = orderedCats

  const rectKeys = useCallback(
    (aRow: number, aMonth: number, bRow: number, bMonth: number): Set<string> => {
      const r1 = Math.min(aRow, bRow)
      const r2 = Math.max(aRow, bRow)
      const m1 = Math.min(aMonth, bMonth)
      const m2 = Math.max(aMonth, bMonth)
      const set = new Set<string>()
      for (let r = r1; r <= r2; r++) {
        for (let m = m1; m <= m2; m++) set.add(cellKey(orderedRef.current[r], m))
      }
      return set
    },
    [],
  )

  // Omhullende rechthoek van de selectie; null zolang de selectie niet exact
  // rechthoekig is (bv. losse Ctrl-klik-cellen) — dan geen vulgreepje.
  const selRect = useMemo((): FillRect | null => {
    if (selected.size === 0) return null
    let r1 = Infinity
    let r2 = -1
    let m1 = 13
    let m2 = 0
    for (const key of selected) {
      const [cid, m] = key.split(':').map(Number)
      const r = rowIndexByCat.get(cid)
      if (r === undefined) return null
      r1 = Math.min(r1, r)
      r2 = Math.max(r2, r)
      m1 = Math.min(m1, m)
      m2 = Math.max(m2, m)
    }
    if ((r2 - r1 + 1) * (m2 - m1 + 1) !== selected.size) return null
    return { r1, r2, m1, m2 }
  }, [selected, rowIndexByCat])

  // Doortrekken (Excel-vulgreepje): sleep het hoekje van de selectie om de
  // waarden patroon-herhalend naar de doelcellen te kopiëren.
  const [fillPreview, setFillPreview] = useState<Set<string> | null>(null)
  const fillingRef = useRef(false)
  const fillRectRef = useRef<FillRect | null>(null)
  const fillTargetRef = useRef<{ row: number; month: number } | null>(null)

  /** Doelcellen (bron uitgezonderd) voor een sleep naar (row, month); horizontaal
   * wint wanneer de muis buiten de maandkolommen van de bron staat. */
  const fillTargetKeys = useCallback(
    (rect: FillRect, row: number, month: number): Set<string> => {
      const set = new Set<string>()
      if (month > rect.m2) {
        for (let r = rect.r1; r <= rect.r2; r++)
          for (let m = rect.m2 + 1; m <= month; m++) set.add(cellKey(orderedRef.current[r], m))
      } else if (month < rect.m1) {
        for (let r = rect.r1; r <= rect.r2; r++)
          for (let m = month; m < rect.m1; m++) set.add(cellKey(orderedRef.current[r], m))
      } else if (row > rect.r2) {
        for (let r = rect.r2 + 1; r <= row; r++)
          for (let m = rect.m1; m <= rect.m2; m++) set.add(cellKey(orderedRef.current[r], m))
      } else if (row < rect.r1) {
        for (let r = row; r < rect.r1; r++)
          for (let m = rect.m1; m <= rect.m2; m++) set.add(cellKey(orderedRef.current[r], m))
      }
      return set
    },
    [],
  )

  const openEditor = useCallback((categoryId: number, month: number, initialText?: string) => {
    const cents = centsRef.current.get(cellKey(categoryId, month)) ?? 0
    setEditText(initialText ?? (cents !== 0 ? String(Math.round(cents / 100)) : ''))
    setInvalid(false)
    setEditing({ categoryId, month })
  }, [])

  const closeEditor = useCallback((key: string) => {
    setEditing((cur) => (cur && cellKey(cur.categoryId, cur.month) === key ? null : cur))
  }, [])

  // Slaat één (heel-euro) bedrag op naar de gegeven cellen. Geeft succes terug.
  const commit = useCallback(
    async (keys: string[], text: string): Promise<boolean> => {
      const parsed = parseEuroToCents(text)
      if (parsed === null) {
        setInvalid(true)
        return false
      }
      const whole = Math.round(parsed / 100) * 100
      setBusy(true)
      try {
        await onSave(
          keys.map((k) => {
            const [cid, m] = k.split(':').map(Number)
            return { category_id: cid, year, month: m, amount_cents: whole }
          }),
        )
        return true
      } catch {
        setInvalid(true)
        return false
      } finally {
        setBusy(false)
      }
    },
    [onSave, year],
  )

  /** Rond het doortrekken af: kopieer de bronwaarden patroon-herhalend (zoals
   * Excel tegelt bij een bron van meerdere cellen) naar de doelcellen. */
  const commitFill = useCallback(async () => {
    const rect = fillRectRef.current
    const target = fillTargetRef.current
    fillingRef.current = false
    fillRectRef.current = null
    fillTargetRef.current = null
    setFillPreview(null)
    if (!rect || !target) return
    const keys = fillTargetKeys(rect, target.row, target.month)
    if (keys.size === 0) return
    const width = rect.m2 - rect.m1 + 1
    const height = rect.r2 - rect.r1 + 1
    const mod = (n: number, d: number) => ((n % d) + d) % d
    const horizontal = target.month > rect.m2 || target.month < rect.m1
    const items = [...keys].map((k) => {
      const [cid, m] = k.split(':').map(Number)
      const r = rowIndexByCat.get(cid) ?? rect.r1
      const srcCid = horizontal ? cid : orderedRef.current[rect.r1 + mod(r - rect.r1, height)]
      const srcMonth = horizontal ? rect.m1 + mod(m - rect.m1, width) : m
      const cents = centsRef.current.get(cellKey(srcCid, srcMonth)) ?? 0
      return { category_id: cid, year, month: m, amount_cents: cents }
    })
    setBusy(true)
    try {
      await onSave(items)
      // Excel-gedrag: na het doortrekken is bron + doel samen geselecteerd.
      setSelected((prev) => new Set([...prev, ...keys]))
    } finally {
      setBusy(false)
    }
  }, [fillTargetKeys, rowIndexByCat, onSave, year])

  const clearCells = useCallback(
    async (keys: string[]) => {
      if (keys.length === 0) return
      setBusy(true)
      try {
        await onSave(
          keys.map((k) => {
            const [cid, m] = k.split(':').map(Number)
            return { category_id: cid, year, month: m, amount_cents: 0 }
          }),
        )
      } finally {
        setBusy(false)
      }
    },
    [onSave, year],
  )

  function onCellMouseDown(
    categoryId: number,
    month: number,
    e: React.MouseEvent<HTMLTableCellElement>,
  ) {
    if (e.button !== 0) return // rechtsklik opent het notitiemenu, geen selectie-sleep
    const row = rowIndexByCat.get(categoryId)
    if (row === undefined) return
    if (e.shiftKey && anchorRef.current) {
      e.preventDefault()
      setSelected(rectKeys(anchorRef.current.row, anchorRef.current.month, row, month))
      return
    }
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault()
      const key = cellKey(categoryId, month)
      setSelected((prev) => {
        const next = new Set(prev)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      })
      anchorRef.current = { row, month }
      return
    }
    // Gewone klik: mogelijk begin van een sleep-selectie; bij loslaten zonder
    // beweging openen we de editor (klik = bewerken).
    anchorRef.current = { row, month }
    draggingRef.current = true
    movedRef.current = false
    setSelected(new Set([cellKey(categoryId, month)]))
  }

  function onCellMouseEnter(categoryId: number, month: number) {
    const row = rowIndexByCat.get(categoryId)
    if (row === undefined) return
    if (fillingRef.current && fillRectRef.current) {
      fillTargetRef.current = { row, month }
      setFillPreview(fillTargetKeys(fillRectRef.current, row, month))
      return
    }
    if (!draggingRef.current || !anchorRef.current) return
    movedRef.current = true
    setSelected(rectKeys(anchorRef.current.row, anchorRef.current.month, row, month))
  }

  function onFillHandleMouseDown(e: React.MouseEvent) {
    // Niet doorgeven aan de cel: het greepje start doortrekken, geen nieuwe selectie.
    e.preventDefault()
    e.stopPropagation()
    if (selRect === null || busy) return
    fillingRef.current = true
    fillRectRef.current = selRect
    fillTargetRef.current = null
    setFillPreview(new Set())
  }

  // Muis loslaten (waar dan ook): doortrekken afronden of sleep beëindigen; een
  // klik zonder beweging → editor.
  useEffect(() => {
    function onUp() {
      if (fillingRef.current) {
        void commitFill()
        return
      }
      if (!draggingRef.current) return
      draggingRef.current = false
      // Klik zonder sleepbeweging → editor openen (een lopende commit van een andere
      // cel sluit zichzelf via closeEditor op key, dus geen conflict).
      if (!movedRef.current && anchorRef.current) {
        const cid = orderedRef.current[anchorRef.current.row]
        if (cid !== undefined) openEditor(cid, anchorRef.current.month)
      }
    }
    window.addEventListener('mouseup', onUp)
    return () => window.removeEventListener('mouseup', onUp)
  }, [openEditor, commitFill])

  // Typen op een selectie zonder open editor: opent de editor op de anker-cel met de
  // ingetypte toets; Delete/Backspace wist de selectie; Esc heft de selectie op.
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape' && fillingRef.current) {
        // Doortrekken annuleren zonder op te slaan.
        fillingRef.current = false
        fillRectRef.current = null
        fillTargetRef.current = null
        setFillPreview(null)
        return
      }
      if (editingRef.current !== null) return
      const sel = selectedRef.current
      if (sel.size === 0) return
      const el = document.activeElement
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) return
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        void clearCells([...sel])
        return
      }
      if (e.key === 'Escape') {
        setSelected(new Set())
        return
      }
      const anchor = anchorRef.current
      if (!anchor) return
      const cid = orderedRef.current[anchor.row]
      if (cid === undefined) return
      if (/^[0-9]$/.test(e.key) || e.key === '-') {
        e.preventDefault()
        openEditor(cid, anchor.month, e.key)
      } else if (e.key === 'Enter') {
        e.preventDefault()
        openEditor(cid, anchor.month)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [openEditor, clearCells])

  // Celnotities (Excel-achtig): gedeeld gedrag met de forecast-tabel.
  const notes = useCellNotes({
    noteFor: (key) => notesByKey.get(key) ?? null,
    onSave: async (key, note) => {
      const [cid, m] = key.split(':').map(Number)
      await onSaveNote({ category_id: cid, year, month: m, note })
    },
    // Rechtsklik selecteert de cel, zoals Excel.
    onMenuOpen: (key) => {
      const [cid, m] = key.split(':').map(Number)
      const row = rowIndexByCat.get(cid)
      if (row !== undefined) {
        anchorRef.current = { row, month: m }
        setSelected(new Set([key]))
      }
    },
  })

  function onEditKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!editing) return
    const key = cellKey(editing.categoryId, editing.month)
    if (e.key === 'Enter') {
      e.preventDefault()
      skipBlurRef.current = true
      const targets = e.ctrlKey || e.metaKey ? [...selectedRef.current] : [key]
      void commit(targets.length ? targets : [key], editText).then((ok) => {
        if (ok) closeEditor(key)
        else skipBlurRef.current = false
      })
    } else if (e.key === 'Escape') {
      e.preventDefault()
      skipBlurRef.current = true
      closeEditor(key)
    }
  }

  function onEditBlur() {
    if (skipBlurRef.current) {
      skipBlurRef.current = false
      return
    }
    if (!editing) return
    const key = cellKey(editing.categoryId, editing.month)
    void commit([key], editText).then((ok) => {
      if (ok) closeEditor(key)
    })
  }

  const cellCtrl: CellController = {
    isSelected: (cid, m) => selected.has(cellKey(cid, m)),
    isEditing: (cid, m) => editing?.categoryId === cid && editing.month === m,
    isFillPreview: (cid, m) => fillPreview?.has(cellKey(cid, m)) ?? false,
    // Het vulgreepje zit op de cel rechtsonder van een rechthoekige selectie.
    hasFillHandle: (cid, m) =>
      !coarse &&
      selRect !== null &&
      !busy &&
      orderedCats[selRect.r2] === cid &&
      selRect.m2 === m,
    editText,
    invalid,
    busy,
    multiCount: selected.size,
    notes,
    onCellMouseDown,
    onCellMouseEnter,
    onFillHandleMouseDown,
    onEditChange: (v) => {
      setEditText(v)
      setInvalid(false)
    },
    onEditKeyDown,
    onEditBlur,
  }

  return (
    <>
    <div className="overflow-x-auto overscroll-x-contain rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[760px] select-none border-collapse text-sm max-md:text-xs">
        <thead>
          <tr className="text-xs text-ink-3">
            <th className="sticky-col px-4 py-3 text-left font-medium max-md:px-3">
              Categorie
            </th>
            {MAAND_KORT.map((m) => (
              <th key={m} className="px-2 py-3 text-right font-medium">
                {m}
              </th>
            ))}
            <th className="px-4 py-3 text-right font-medium">Totaal</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          <tr className="border-t border-line">
            <td className="sticky-col px-4 py-2.5 font-medium max-md:px-3">
              Te verdelen
            </td>
            {matrix.to_be_allocated_cents.map((cents, i) => (
              <td key={i} className={`px-2 py-2.5 text-right ${tbaClass(cents)}`}>
                {formatCentsWhole(cents)}
              </td>
            ))}
            <td
              className={`px-4 py-2.5 text-right font-medium ${tbaClass(
                matrix.to_be_allocated_total_cents,
              )}`}
            >
              {formatCentsWhole(matrix.to_be_allocated_total_cents)}
            </td>
          </tr>

          {matrix.groups.map((group) => (
            <GroupRows
              key={group.type}
              group={group}
              ctrl={cellCtrl}
              onAddCategory={onAddCategory}
              onDeleteCategory={onDeleteCategory}
            />
          ))}
        </tbody>
      </table>
    </div>

    {notes.overlays}
    </>
  )
}

function tbaClass(cents: number): string {
  if (cents < 0) return 'text-crit'
  if (cents > 0) return 'text-good'
  return 'text-ink-3'
}

interface CellController {
  isSelected: (categoryId: number, month: number) => boolean
  isEditing: (categoryId: number, month: number) => boolean
  isFillPreview: (categoryId: number, month: number) => boolean
  hasFillHandle: (categoryId: number, month: number) => boolean
  editText: string
  invalid: boolean
  busy: boolean
  multiCount: number
  notes: CellNotes
  onCellMouseDown: (
    categoryId: number,
    month: number,
    e: React.MouseEvent<HTMLTableCellElement>,
  ) => void
  onCellMouseEnter: (categoryId: number, month: number) => void
  onFillHandleMouseDown: (e: React.MouseEvent) => void
  onEditChange: (value: string) => void
  onEditKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void
  onEditBlur: () => void
}

function GroupRows({
  group,
  ctrl,
  onAddCategory,
  onDeleteCategory,
}: {
  group: BudgetMatrix['groups'][number]
  ctrl: CellController
  onAddCategory: (type: CategoryType, name: string) => Promise<boolean>
  onDeleteCategory: (id: number, name: string) => void
}) {
  return (
    <>
      <tr className="border-t border-line">
        <td
          colSpan={14}
          className="sticky-col px-4 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-ink-3 max-md:px-3"
        >
          {group.type}
        </td>
      </tr>
      {group.categories.map((row) => (
        <tr key={row.category_id} className="group/row">
          <td className="sticky-col px-4 py-1 text-ink-2 max-md:px-3">
            <div className="flex items-center gap-2">
              <span className="max-w-48 truncate max-md:max-w-28">{row.name}</span>
              <button
                onClick={() => onDeleteCategory(row.category_id, row.name)}
                aria-label={`Categorie ${row.name} verwijderen`}
                title="Categorie verwijderen"
                className="px-1 text-ink-3 opacity-0 transition-opacity hover:text-crit group-hover/row:opacity-100 pointer-coarse:opacity-100"
              >
                ×
              </button>
            </div>
          </td>
          {row.month_cents.map((cents, monthIdx) => (
            <Cell
              key={monthIdx}
              categoryId={row.category_id}
              month={monthIdx + 1}
              cents={cents}
              ctrl={ctrl}
            />
          ))}
          <td className="px-4 py-1 text-right text-ink-2">
            {row.total_cents !== 0 ? formatCentsWhole(row.total_cents) : ''}
          </td>
        </tr>
      ))}
      <AddCategoryRow type={group.type} onAdd={onAddCategory} />
      <tr className="border-t border-line/60">
        <td className="sticky-col px-4 py-2 text-xs text-ink-3 max-md:px-3">
          Totaal {group.type.toLowerCase()}
        </td>
        {group.monthly_total_cents.map((cents, i) => (
          <td key={i} className="px-2 py-2 text-right text-xs text-ink-3">
            {cents !== 0 ? formatCentsWhole(cents) : ''}
          </td>
        ))}
        <td className="px-4 py-2 text-right text-xs text-ink-3">
          {formatCentsWhole(group.total_cents)}
        </td>
      </tr>
    </>
  )
}

function Cell({
  categoryId,
  month,
  cents,
  ctrl,
}: {
  categoryId: number
  month: number
  cents: number
  ctrl: CellController
}) {
  const selected = ctrl.isSelected(categoryId, month)
  const editing = ctrl.isEditing(categoryId, month)

  if (editing) {
    return (
      <td className="p-0">
        <input
          autoFocus
          inputMode="decimal"
          value={ctrl.editText}
          disabled={ctrl.busy}
          onChange={(e) => ctrl.onEditChange(e.target.value)}
          onKeyDown={ctrl.onEditKeyDown}
          onBlur={ctrl.onEditBlur}
          aria-invalid={ctrl.invalid}
          title={
            ctrl.multiCount > 1
              ? `Ctrl+Enter vult ${ctrl.multiCount} cellen`
              : undefined
          }
          className={`w-full rounded border bg-page px-2 py-1 text-right focus:outline-none ${
            ctrl.invalid ? 'border-crit' : 'border-accent'
          } ${ctrl.busy ? 'opacity-50' : ''}`}
        />
      </td>
    )
  }

  const key = cellKey(categoryId, month)
  const fillPreview = ctrl.isFillPreview(categoryId, month)

  return (
    <td
      onMouseDown={(e) => ctrl.onCellMouseDown(categoryId, month, e)}
      onMouseEnter={(e) => {
        ctrl.onCellMouseEnter(categoryId, month)
        ctrl.notes.onHoverStart(key, e)
      }}
      onMouseLeave={() => ctrl.notes.onHoverEnd(key)}
      onContextMenu={(e) => ctrl.notes.onContextMenu(key, e)}
      {...ctrl.notes.longPress(key)}
      className={`no-callout relative cursor-cell px-2 py-1 text-right transition-colors max-md:px-1.5 ${
        selected
          ? 'bg-accent/15 ring-1 ring-inset ring-accent'
          : fillPreview
            ? 'bg-accent/5 ring-1 ring-inset ring-accent/50'
            : 'hover:bg-raised'
      }`}
    >
      {ctrl.notes.hasNote(key) && <NoteMarker />}
      {cents !== 0 ? formatCentsWhole(cents) : <span className="text-ink-3">·</span>}
      {ctrl.hasFillHandle(categoryId, month) && (
        <span
          onMouseDown={ctrl.onFillHandleMouseDown}
          title="Doortrekken: sleep om de waarden te kopiëren"
          className="absolute -bottom-[3px] -right-[3px] z-10 size-2 cursor-crosshair border border-white bg-accent"
        />
      )}
    </td>
  )
}

function AddCategoryRow({
  type,
  onAdd,
}: {
  type: CategoryType
  onAdd: (type: CategoryType, name: string) => Promise<boolean>
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  function close() {
    setOpen(false)
    setName('')
  }

  async function submit() {
    const trimmed = name.trim()
    if (!trimmed) return
    setBusy(true)
    const ok = await onAdd(type, trimmed)
    setBusy(false)
    if (ok) close()
  }

  return (
    <tr>
      <td colSpan={14} className="sticky-col px-4 py-1.5 max-md:px-3">
        {open ? (
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={name}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void submit()
                } else if (e.key === 'Escape') {
                  close()
                }
              }}
              placeholder={`Nieuwe ${type.toLowerCase()}-categorie`}
              className="w-56 rounded-lg border border-accent bg-page px-2 py-1 text-sm focus:outline-none"
            />
            <button
              onClick={() => void submit()}
              disabled={busy}
              className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent/85 disabled:opacity-50"
            >
              Toevoegen
            </button>
            <button onClick={close} className="text-xs text-ink-3 hover:text-ink-2">
              Annuleren
            </button>
          </div>
        ) : (
          <button onClick={() => setOpen(true)} className="text-xs text-ink-3 hover:text-accent">
            + categorie
          </button>
        )}
      </td>
    </tr>
  )
}
