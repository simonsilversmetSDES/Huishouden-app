// Zoekbare categoriekiezer (combobox met type-ahead): typ "katten" → Katten.
// De dropdown wordt via een portal op document.body gerenderd zodat hij niet
// geknipt wordt door overflow-containers (bv. de scrollbare import-tabel).

import { useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import type { Category, CategoryType } from '../api/types'

const TYPE_ORDER: CategoryType[] = ['Inkomen', 'Uitgaven', 'Sparen']

interface Option {
  id: number | null
  label: string
  type: CategoryType | null
}

interface Coords {
  top: number
  left: number
  width: number
}

interface CategoryPickerProps {
  categories: Category[]
  value: number | null
  onChange: (id: number | null) => void
  placeholder?: string
  allowEmpty?: boolean
  emptyLabel?: string
  groupByType?: boolean
  ariaLabel?: string
  className?: string
  wrapperClassName?: string
}

export default function CategoryPicker({
  categories,
  value,
  onChange,
  placeholder = 'Kies categorie…',
  allowEmpty = false,
  emptyLabel = '— geen —',
  groupByType = false,
  ariaLabel,
  className = '',
  wrapperClassName = 'w-full',
}: CategoryPickerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const [coords, setCoords] = useState<Coords | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const selectedLabel = value === null ? '' : (categories.find((c) => c.id === value)?.name ?? '')

  const options = useMemo<Option[]>(() => {
    const q = query.trim().toLowerCase()
    let cats = categories.filter((c) => c.name.toLowerCase().includes(q))
    if (groupByType) {
      cats = [...cats].sort((a, b) => TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type))
    }
    const opts: Option[] = cats.map((c) => ({ id: c.id, label: c.name, type: c.type }))
    // "leeg maken" enkel tonen bij een lege zoekterm — anders zou de eerste
    // (gemarkeerde) optie het wissen zijn i.p.v. de eerste match.
    if (allowEmpty && q === '') opts.unshift({ id: null, label: emptyLabel, type: null })
    return opts
  }, [categories, query, groupByType, allowEmpty, emptyLabel])

  function reposition() {
    const el = wrapRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setCoords({ top: r.bottom + 4, left: r.left, width: r.width })
  }

  useLayoutEffect(() => {
    if (!open) return
    reposition()
    const onScrollOrResize = () => reposition()
    // capture=true: ook scrollen binnen ancestor-overflow (import-tabel) volgen
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
    function onDown(e: MouseEvent) {
      const t = e.target as Node
      if (wrapRef.current?.contains(t) || listRef.current?.contains(t)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('scroll', onScrollOrResize, true)
      window.removeEventListener('resize', onScrollOrResize)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  function openList() {
    setQuery('')
    setHighlight(0)
    setOpen(true)
  }

  function choose(opt: Option) {
    onChange(opt.id)
    setOpen(false)
    setQuery('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) {
      openList()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => Math.min(h + 1, options.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const opt = options[highlight]
      if (opt) choose(opt)
    } else if (e.key === 'Escape') {
      setOpen(false)
      setQuery('')
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div ref={wrapRef} className={`relative ${wrapperClassName}`}>
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-label={ariaLabel}
        value={open ? query : selectedLabel}
        placeholder={open ? selectedLabel || placeholder : selectedLabel ? '' : placeholder}
        onChange={(e) => {
          setQuery(e.target.value)
          setHighlight(0)
          if (!open) setOpen(true)
        }}
        onFocus={openList}
        onClick={() => {
          if (!open) openList()
        }}
        onKeyDown={onKeyDown}
        className={className}
      />
      {open &&
        coords &&
        createPortal(
          <div
            ref={listRef}
            style={{
              position: 'fixed',
              top: coords.top,
              left: coords.left,
              width: coords.width,
              zIndex: 50,
            }}
            className="max-h-64 overflow-y-auto rounded-lg border border-edge bg-surface py-1 shadow-lg"
          >
            {options.length === 0 ? (
              <p className="px-3 py-2 text-sm text-ink-3">Geen categorie gevonden</p>
            ) : (
              options.map((opt, i) => {
                const header =
                  groupByType && opt.type !== null && (i === 0 || options[i - 1].type !== opt.type)
                return (
                  <div key={opt.id ?? 'empty'}>
                    {header && (
                      <div className="px-3 pb-0.5 pt-1.5 text-[11px] uppercase tracking-wide text-ink-3">
                        {opt.type}
                      </div>
                    )}
                    <button
                      type="button"
                      onMouseEnter={() => setHighlight(i)}
                      onClick={() => choose(opt)}
                      className={`block w-full px-3 py-1.5 text-left text-sm ${
                        i === highlight ? 'bg-raised text-ink' : 'text-ink-2'
                      } ${opt.id === null ? 'italic text-ink-3' : ''}`}
                    >
                      {opt.label}
                    </button>
                  </div>
                )
              })
            )}
          </div>,
          document.body,
        )}
    </div>
  )
}
