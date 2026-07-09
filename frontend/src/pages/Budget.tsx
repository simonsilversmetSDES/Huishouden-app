import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'
import { createPortal } from 'react-dom'
import { api, ApiError } from '../api/client'
import type {
  BudgetCellUpdate,
  BudgetMatrix,
  BudgetNotePayload,
  Category,
  CategoryPayload,
  CategoryType,
} from '../api/types'
import { formatCentsWhole, MAAND_KORT, parseEuroToCents } from '../lib/format'
import { useAppState } from '../state/AppState'

export default function Budget() {
  const { contextId } = useAppState()
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [matrix, setMatrix] = useState<BudgetMatrix | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [catError, setCatError] = useState<string | null>(null)

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
    },
    [load],
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
      } catch {
        setCatError('Categorie verwijderen mislukt — probeer opnieuw')
      }
    },
    [load],
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
        selecteren · typ een bedrag en <strong>Ctrl+Enter</strong> vult alle geselecteerde
        cellen · <strong>Delete</strong> wist de selectie · Enter = opslaan · Esc = annuleren ·
        rechtsklik = notitie
      </p>
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

  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [editing, setEditing] = useState<{ categoryId: number; month: number } | null>(null)
  const [editText, setEditText] = useState('')
  const [invalid, setInvalid] = useState(false)
  const [busy, setBusy] = useState(false)

  // Celnotities (Excel-achtig): rechtsklikmenu, notitie-popover en hover-tooltip.
  const [menu, setMenu] = useState<{ x: number; y: number; categoryId: number; month: number } | null>(null)
  const [noteEdit, setNoteEdit] = useState<{ categoryId: number; month: number; x: number; y: number } | null>(null)
  const [noteText, setNoteText] = useState('')
  const [noteBusy, setNoteBusy] = useState(false)
  const [hoverNote, setHoverNote] = useState<{ text: string; x: number; y: number } | null>(null)

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
    if (!draggingRef.current || !anchorRef.current) return
    const row = rowIndexByCat.get(categoryId)
    if (row === undefined) return
    movedRef.current = true
    setSelected(rectKeys(anchorRef.current.row, anchorRef.current.month, row, month))
  }

  // Muis loslaten (waar dan ook): sleep beëindigen; een klik zonder beweging → editor.
  useEffect(() => {
    function onUp() {
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
  }, [openEditor])

  // Typen op een selectie zonder open editor: opent de editor op de anker-cel met de
  // ingetypte toets; Delete/Backspace wist de selectie; Esc heft de selectie op.
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
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

  // Rechtsklik: cel selecteren (zoals Excel) en het notitiemenu op de cursor openen.
  function onCellContextMenu(
    categoryId: number,
    month: number,
    e: React.MouseEvent<HTMLTableCellElement>,
  ) {
    e.preventDefault()
    const row = rowIndexByCat.get(categoryId)
    if (row !== undefined) {
      anchorRef.current = { row, month }
      setSelected(new Set([cellKey(categoryId, month)]))
    }
    setHoverNote(null)
    setMenu({ x: Math.min(e.clientX, window.innerWidth - 200), y: e.clientY, categoryId, month })
  }

  // Menu sluit bij klik elders of Escape (mousedown op het menu zelf stopt de bubble).
  useEffect(() => {
    if (!menu) return
    const close = () => setMenu(null)
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(null)
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [menu])

  function openNoteEditor() {
    if (!menu) return
    setNoteText(notesByKey.get(cellKey(menu.categoryId, menu.month)) ?? '')
    setNoteEdit({
      categoryId: menu.categoryId,
      month: menu.month,
      x: Math.min(menu.x, window.innerWidth - 300),
      y: menu.y,
    })
    setMenu(null)
  }

  async function saveNote(text: string) {
    if (!noteEdit) return
    setNoteBusy(true)
    try {
      await onSaveNote({
        category_id: noteEdit.categoryId,
        year,
        month: noteEdit.month,
        note: text,
      })
      setNoteEdit(null)
    } finally {
      setNoteBusy(false)
    }
  }

  function removeNoteFromMenu() {
    if (!menu) return
    const { categoryId, month } = menu
    setMenu(null)
    void onSaveNote({ category_id: categoryId, year, month, note: '' })
  }

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
    noteFor: (cid, m) => notesByKey.get(cellKey(cid, m)) ?? null,
    editText,
    invalid,
    busy,
    multiCount: selected.size,
    onCellMouseDown,
    onCellMouseEnter,
    onCellContextMenu,
    onNoteHover: setHoverNote,
    onEditChange: (v) => {
      setEditText(v)
      setInvalid(false)
    },
    onEditKeyDown,
    onEditBlur,
  }

  const menuHasNote = menu !== null && notesByKey.has(cellKey(menu.categoryId, menu.month))

  return (
    <>
    <div className="overflow-x-auto rounded-2xl border border-edge bg-surface">
      <table className="w-full min-w-[760px] select-none border-collapse text-sm">
        <thead>
          <tr className="text-xs text-ink-3">
            <th className="sticky left-0 z-10 bg-surface px-4 py-3 text-left font-medium">
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
            <td className="sticky left-0 z-10 bg-surface px-4 py-2.5 font-medium">
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

    {/* Overlays via een portal naar <body>: de matrix-container heeft een CSS-transform
        (-translate-x-1/2) en die maakt position:fixed anders relatief aan de container. */}
    {menu && createPortal(
      <div
        onMouseDown={(e) => e.stopPropagation()}
        className="fixed z-50 min-w-44 rounded-lg border border-edge bg-surface py-1 text-sm shadow-lg"
        style={{ left: menu.x, top: menu.y }}
      >
        <button
          onClick={openNoteEditor}
          className="block w-full px-3 py-1.5 text-left hover:bg-raised"
        >
          {menuHasNote ? 'Notitie bewerken' : 'Notitie toevoegen'}
        </button>
        {menuHasNote && (
          <button
            onClick={removeNoteFromMenu}
            className="block w-full px-3 py-1.5 text-left text-crit hover:bg-raised"
          >
            Notitie verwijderen
          </button>
        )}
      </div>,
      document.body,
    )}

    {/* Notitie-editor (Excel-achtige gele post-it) */}
    {noteEdit && createPortal(
      <div
        className="fixed z-50 w-72 rounded-lg border border-warn/50 bg-[#fdf6d8] p-2 shadow-lg"
        style={{ left: noteEdit.x, top: noteEdit.y }}
      >
        <textarea
          autoFocus
          rows={4}
          value={noteText}
          disabled={noteBusy}
          onChange={(e) => setNoteText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault()
              setNoteEdit(null)
            } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              e.preventDefault()
              void saveNote(noteText)
            }
          }}
          placeholder="Notitie…"
          className="w-full resize-none bg-transparent text-sm text-ink focus:outline-none"
        />
        <div className="mt-1 flex items-center gap-2">
          <button
            onClick={() => void saveNote(noteText)}
            disabled={noteBusy}
            className="rounded bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent/85 disabled:opacity-50"
          >
            Opslaan
          </button>
          <button
            onClick={() => setNoteEdit(null)}
            disabled={noteBusy}
            className="text-xs text-ink-3 hover:text-ink-2"
          >
            Annuleren
          </button>
          <span className="ml-auto text-[10px] text-ink-3">Ctrl+Enter = opslaan</span>
        </div>
      </div>,
      document.body,
    )}

    {/* Hover-tooltip met de notitie-inhoud */}
    {hoverNote && !menu && !noteEdit && createPortal(
      <div
        className="pointer-events-none fixed z-40 max-w-72 whitespace-pre-wrap rounded-lg border border-warn/50 bg-[#fdf6d8] px-3 py-2 text-xs text-ink shadow-lg"
        style={{ left: hoverNote.x, top: hoverNote.y + 4 }}
      >
        {hoverNote.text}
      </div>,
      document.body,
    )}
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
  noteFor: (categoryId: number, month: number) => string | null
  editText: string
  invalid: boolean
  busy: boolean
  multiCount: number
  onCellMouseDown: (
    categoryId: number,
    month: number,
    e: React.MouseEvent<HTMLTableCellElement>,
  ) => void
  onCellMouseEnter: (categoryId: number, month: number) => void
  onCellContextMenu: (
    categoryId: number,
    month: number,
    e: React.MouseEvent<HTMLTableCellElement>,
  ) => void
  onNoteHover: (info: { text: string; x: number; y: number } | null) => void
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
          className="sticky left-0 bg-surface px-4 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-ink-3"
        >
          {group.type}
        </td>
      </tr>
      {group.categories.map((row) => (
        <tr key={row.category_id} className="group/row">
          <td className="sticky left-0 z-10 bg-surface px-4 py-1 text-ink-2">
            <div className="flex items-center gap-2">
              <span className="max-w-48 truncate">{row.name}</span>
              <button
                onClick={() => onDeleteCategory(row.category_id, row.name)}
                aria-label={`Categorie ${row.name} verwijderen`}
                title="Categorie verwijderen"
                className="text-ink-3 opacity-0 transition-opacity hover:text-crit group-hover/row:opacity-100"
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
        <td className="sticky left-0 z-10 bg-surface px-4 py-2 text-xs text-ink-3">
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

  const note = ctrl.noteFor(categoryId, month)

  return (
    <td
      onMouseDown={(e) => ctrl.onCellMouseDown(categoryId, month, e)}
      onMouseEnter={(e) => {
        ctrl.onCellMouseEnter(categoryId, month)
        if (note !== null) {
          const r = e.currentTarget.getBoundingClientRect()
          ctrl.onNoteHover({ text: note, x: r.left, y: r.bottom })
        }
      }}
      onMouseLeave={() => {
        if (note !== null) ctrl.onNoteHover(null)
      }}
      onContextMenu={(e) => ctrl.onCellContextMenu(categoryId, month, e)}
      className={`relative cursor-cell px-2 py-1 text-right transition-colors ${
        selected ? 'bg-accent/15 ring-1 ring-inset ring-accent' : 'hover:bg-raised'
      }`}
    >
      {note !== null && (
        <span
          aria-hidden
          className="pointer-events-none absolute right-0 top-0 border-l-[6px] border-t-[6px] border-l-transparent border-t-crit"
        />
      )}
      {cents !== 0 ? formatCentsWhole(cents) : <span className="text-ink-3">·</span>}
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
      <td colSpan={14} className="sticky left-0 bg-surface px-4 py-1.5">
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
