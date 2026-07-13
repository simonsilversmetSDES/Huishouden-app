// Excel-achtige celnotities, gedeeld door de budget- en forecast-tabellen:
// rechtsklikmenu (toevoegen/bewerken/verwijderen), geel notitie-kadertje en
// hover-tooltip. Op touch opent lang indrukken hetzelfde menu (rechtsklik en
// hover bestaan daar niet). De overlays gaan via een portal naar <body>, omdat
// een CSS-transform op een tabelcontainer position:fixed anders verschuift.

import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useLongPress, type LongPressHandlers } from '../lib/useLongPress'
import { useIsMobile } from '../lib/useMediaQuery'

interface CellNotesOptions {
  /** Huidige notitie voor een celsleutel, of null. */
  noteFor: (key: string) => string | null
  /** Notitie opslaan; lege string = verwijderen. */
  onSave: (key: string, note: string) => Promise<void>
  /** Bij het openen van het menu (bv. de cel selecteren, zoals Excel doet). */
  onMenuOpen?: (key: string) => void
}

export interface CellNotes {
  hasNote: (key: string) => boolean
  onContextMenu: (key: string, e: React.MouseEvent) => void
  /** Touch-handlers per cel: lang indrukken opent het notitiemenu. */
  longPress: (key: string) => LongPressHandlers
  onHoverStart: (key: string, e: React.MouseEvent) => void
  onHoverEnd: (key: string) => void
  overlays: ReactNode
}

export function useCellNotes({ noteFor, onSave, onMenuOpen }: CellNotesOptions): CellNotes {
  const isMobile = useIsMobile()
  const { bind: bindLongPress } = useLongPress()
  const [menu, setMenu] = useState<{ x: number; y: number; key: string } | null>(null)
  const [edit, setEdit] = useState<{ key: string; x: number; y: number } | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [hover, setHover] = useState<{ text: string; x: number; y: number } | null>(null)

  // Menu sluit bij klik/tik elders of Escape (mousedown op het menu zelf stopt de bubble).
  useEffect(() => {
    if (!menu) return
    const close = () => setMenu(null)
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(null)
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('touchstart', close)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('touchstart', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [menu])

  // Gedeeld door rechtsklik en long-press; clampt op beide assen zodat het
  // menu onderaan/rechts niet buiten het scherm valt.
  function openMenuAt(key: string, x: number, y: number) {
    onMenuOpen?.(key)
    setHover(null)
    setMenu({
      x: Math.min(x, window.innerWidth - 200),
      y: Math.min(y, window.innerHeight - 110),
      key,
    })
  }

  function onContextMenu(key: string, e: React.MouseEvent) {
    e.preventDefault()
    openMenuAt(key, e.clientX, e.clientY)
  }

  function longPress(key: string): LongPressHandlers {
    return bindLongPress((x, y) => openMenuAt(key, x, y))
  }

  function onHoverStart(key: string, e: React.MouseEvent) {
    const note = noteFor(key)
    if (note === null) return
    const r = e.currentTarget.getBoundingClientRect()
    setHover({ text: note, x: r.left, y: r.bottom })
  }

  function onHoverEnd(key: string) {
    if (noteFor(key) !== null) setHover(null)
  }

  function openEditor() {
    if (!menu) return
    setText(noteFor(menu.key) ?? '')
    setEdit({ key: menu.key, x: Math.min(menu.x, window.innerWidth - 300), y: menu.y })
    setMenu(null)
  }

  async function save(value: string) {
    if (!edit) return
    setBusy(true)
    try {
      await onSave(edit.key, value)
      setEdit(null)
    } finally {
      setBusy(false)
    }
  }

  function removeFromMenu() {
    if (!menu) return
    const key = menu.key
    setMenu(null)
    void onSave(key, '')
  }

  const menuHasNote = menu !== null && noteFor(menu.key) !== null

  const overlays = (
    <>
      {menu &&
        createPortal(
          <div
            onMouseDown={(e) => e.stopPropagation()}
            onTouchStart={(e) => e.stopPropagation()}
            className="fixed z-50 min-w-44 rounded-lg border border-edge bg-surface py-1 text-sm shadow-lg"
            style={{ left: menu.x, top: menu.y }}
          >
            <button
              onClick={openEditor}
              className="block w-full px-3 py-1.5 text-left hover:bg-raised pointer-coarse:py-2.5"
            >
              {menuHasNote ? 'Notitie bewerken' : 'Notitie toevoegen'}
            </button>
            {menuHasNote && (
              <button
                onClick={removeFromMenu}
                className="block w-full px-3 py-1.5 text-left text-crit hover:bg-raised pointer-coarse:py-2.5"
              >
                Notitie verwijderen
              </button>
            )}
          </div>,
          document.body,
        )}

      {edit &&
        createPortal(
          <div
            // Mobiel: vaste strook boven de tabbar i.p.v. op cursorpositie,
            // anders verdwijnt de editor achter het toetsenbord.
            className={`fixed z-50 rounded-lg border border-warn/50 bg-[#fdf6d8] p-2 shadow-lg ${
              isMobile ? 'inset-x-2 bottom-[calc(4rem+env(safe-area-inset-bottom))]' : 'w-72'
            }`}
            style={isMobile ? undefined : { left: edit.x, top: edit.y }}
          >
            <textarea
              autoFocus
              rows={4}
              value={text}
              disabled={busy}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.preventDefault()
                  setEdit(null)
                } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault()
                  void save(text)
                }
              }}
              placeholder="Notitie…"
              className="w-full resize-none bg-transparent text-sm text-ink focus:outline-none"
            />
            <div className="mt-1 flex items-center gap-2">
              <button
                onClick={() => void save(text)}
                disabled={busy}
                className="rounded bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent/85 disabled:opacity-50"
              >
                Opslaan
              </button>
              <button
                onClick={() => setEdit(null)}
                disabled={busy}
                className="text-xs text-ink-3 hover:text-ink-2"
              >
                Annuleren
              </button>
              <span className="ml-auto text-[10px] text-ink-3">Ctrl+Enter = opslaan</span>
            </div>
          </div>,
          document.body,
        )}

      {hover &&
        !menu &&
        !edit &&
        createPortal(
          <div
            className="pointer-events-none fixed z-40 max-w-72 whitespace-pre-wrap rounded-lg border border-warn/50 bg-[#fdf6d8] px-3 py-2 text-xs text-ink shadow-lg"
            style={{ left: hover.x, top: hover.y + 4 }}
          >
            {hover.text}
          </div>,
          document.body,
        )}
    </>
  )

  return {
    hasNote: (key) => noteFor(key) !== null,
    onContextMenu,
    longPress,
    onHoverStart,
    onHoverEnd,
    overlays,
  }
}

/** Rood driehoekje in de celhoek dat een notitie aankondigt (zoals Excel).
 * De omringende cel moet position:relative hebben. */
export function NoteMarker() {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute right-0 top-0 border-l-[6px] border-t-[6px] border-l-transparent border-t-crit"
    />
  )
}
