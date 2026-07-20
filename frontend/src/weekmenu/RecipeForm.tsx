// Gedeeld review/bewerk-formulier voor recepten: alles bewerkbaar vóór opslaan.
// Gebruikt door RecipeNew (na parse of handmatig) en RecipeEdit.

import { useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { photoUrl } from './api'
import { readImageFile, type UploadedImage } from './imageUpload'
import type { Attribute, IngredientIn, RecipePayload } from './types'
import { inputClass, primaryButtonClass, secondaryButtonClass } from './ui'
import type { Attributes } from './useAttributes'

export interface FormInitial {
  title: string
  description: string
  source_url: string
  moment_id: number | null
  category_id: number | null
  time_id: number | null
  difficulty_id: number | null
  ingredients: IngredientIn[]
}

export const EMPTY_INITIAL: FormInitial = {
  title: '',
  description: '',
  source_url: '',
  moment_id: null,
  category_id: null,
  time_id: null,
  difficulty_id: null,
  ingredients: [],
}

/** Fototoestand van het formulier; 'keep'/'remove' bestaan alleen in bewerkmodus. */
export type PhotoState =
  | { kind: 'none' }
  | { kind: 'keep'; path: string }
  | { kind: 'url'; url: string }
  | { kind: 'upload'; image: UploadedImage }
  | { kind: 'remove' }

interface IngredientRowState {
  name: string
  quantity: string
  unit: string
  note: string
}

function toRowState(items: IngredientIn[]): IngredientRowState[] {
  return items.map((item) => ({
    name: item.name,
    quantity: item.quantity ?? '',
    unit: item.unit ?? '',
    note: item.note ?? '',
  }))
}

const orNull = (value: string): string | null => (value.trim() === '' ? null : value.trim())

export default function RecipeForm({
  initial,
  initialPhoto,
  attributes,
  submitLabel,
  onSubmit,
}: {
  initial: FormInitial
  initialPhoto: PhotoState
  attributes: Attributes
  submitLabel: string
  onSubmit: (payload: RecipePayload) => Promise<void>
}) {
  const [title, setTitle] = useState(initial.title)
  const [description, setDescription] = useState(initial.description)
  const [sourceUrl, setSourceUrl] = useState(initial.source_url)
  const [momentId, setMomentId] = useState(initial.moment_id)
  const [categoryId, setCategoryId] = useState(initial.category_id)
  const [timeId, setTimeId] = useState(initial.time_id)
  const [difficultyId, setDifficultyId] = useState(initial.difficulty_id)
  const [rows, setRows] = useState<IngredientRowState[]>(toRowState(initial.ingredients))
  const [photo, setPhoto] = useState<PhotoState>(initialPhoto)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Bewerkmodus: de bestaande foto waarnaar 'Ongedaan maken' terugkeert.
  const originalPath = initialPhoto.kind === 'keep' ? initialPhoto.path : null

  function updateRow(index: number, patch: Partial<IngredientRowState>) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  async function pickFile(file: File | undefined) {
    if (!file) return
    setError(null)
    try {
      setPhoto({ kind: 'upload', image: await readImageFile(file) })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Afbeelding lezen mislukt')
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (title.trim() === '') {
      setError('Titel is verplicht')
      return
    }
    setError(null)
    setSaving(true)
    const payload: RecipePayload = {
      title: title.trim(),
      description,
      source_url: orNull(sourceUrl),
      photo_url: photo.kind === 'url' ? orNull(photo.url) : null,
      photo_base64: photo.kind === 'upload' ? photo.image.base64 : null,
      photo_media_type: photo.kind === 'upload' ? photo.image.mediaType : null,
      moment_id: momentId,
      category_id: categoryId,
      time_id: timeId,
      difficulty_id: difficultyId,
      ingredients: rows
        .filter((row) => row.name.trim() !== '')
        .map((row) => ({
          name: row.name.trim(),
          quantity: orNull(row.quantity),
          unit: orNull(row.unit),
          note: orNull(row.note),
        })),
      remove_photo: photo.kind === 'remove',
    }
    try {
      await onSubmit(payload)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Opslaan mislukt — probeer opnieuw')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <section className="space-y-3 rounded-2xl border border-edge bg-surface p-5">
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Titel</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputClass}
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <AttributeSelect
            label="Moment"
            options={attributes.moments}
            value={momentId}
            onChange={setMomentId}
          />
          <AttributeSelect
            label="Categorie"
            options={attributes.categories}
            value={categoryId}
            onChange={setCategoryId}
          />
          <AttributeSelect
            label="Tijd"
            options={attributes.times}
            value={timeId}
            onChange={setTimeId}
          />
          <AttributeSelect
            label="Moeilijkheid"
            options={attributes.difficulties}
            value={difficultyId}
            onChange={setDifficultyId}
          />
        </div>

        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Bron-URL</span>
          <input
            type="url"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://…"
            className={inputClass}
          />
        </label>
      </section>

      <section className="space-y-3 rounded-2xl border border-edge bg-surface p-5">
        <h2 className="text-sm font-medium">Foto</h2>
        <PhotoPreview photo={photo} />
        <div className="flex flex-wrap items-center gap-2">
          {photo.kind === 'keep' && (
            <button
              type="button"
              onClick={() => setPhoto({ kind: 'remove' })}
              className={secondaryButtonClass}
            >
              Foto verwijderen
            </button>
          )}
          {photo.kind === 'remove' && (
            <button
              type="button"
              onClick={() =>
                setPhoto(originalPath ? { kind: 'keep', path: originalPath } : { kind: 'none' })
              }
              className={secondaryButtonClass}
            >
              Ongedaan maken
            </button>
          )}
          {(photo.kind === 'url' || photo.kind === 'upload') && (
            <button
              type="button"
              onClick={() =>
                setPhoto(originalPath ? { kind: 'keep', path: originalPath } : { kind: 'none' })
              }
              className={secondaryButtonClass}
            >
              Wissen
            </button>
          )}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className={secondaryButtonClass}
          >
            {photo.kind === 'upload' ? 'Andere afbeelding…' : 'Afbeelding uploaden…'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => {
              void pickFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>
        {photo.kind !== 'upload' && photo.kind !== 'remove' && (
          <label className="block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
              {photo.kind === 'keep' ? 'Vervangen door foto-URL' : 'Foto-URL'}
            </span>
            <input
              type="url"
              value={photo.kind === 'url' ? photo.url : ''}
              onChange={(e) => {
                const url = e.target.value
                setPhoto(
                  url === ''
                    ? originalPath
                      ? { kind: 'keep', path: originalPath }
                      : { kind: 'none' }
                    : { kind: 'url', url },
                )
              }}
              placeholder="https://…"
              className={inputClass}
            />
          </label>
        )}
        {photo.kind === 'remove' && (
          <p className="text-sm text-ink-3">De huidige foto wordt verwijderd bij het opslaan.</p>
        )}
      </section>

      <section className="space-y-3 rounded-2xl border border-edge bg-surface p-5">
        <h2 className="text-sm font-medium">Ingrediënten</h2>
        {rows.length === 0 && <p className="text-sm text-ink-3">Nog geen ingrediënten.</p>}
        <div className="space-y-2">
          {rows.map((row, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                value={row.quantity}
                onChange={(e) => updateRow(index, { quantity: e.target.value })}
                placeholder="Hoev."
                aria-label="Hoeveelheid"
                className={`${inputClass} w-20 text-right tabular-nums`}
              />
              <input
                type="text"
                value={row.unit}
                onChange={(e) => updateRow(index, { unit: e.target.value })}
                placeholder="Eenheid"
                aria-label="Eenheid"
                className={`${inputClass} w-24`}
              />
              <input
                type="text"
                value={row.name}
                onChange={(e) => updateRow(index, { name: e.target.value })}
                placeholder="Ingrediënt"
                aria-label="Ingrediënt"
                className={`${inputClass} min-w-36 flex-1`}
              />
              <input
                type="text"
                value={row.note}
                onChange={(e) => updateRow(index, { note: e.target.value })}
                placeholder="Notitie"
                aria-label="Notitie"
                className={`${inputClass} w-full sm:w-40`}
              />
              <button
                type="button"
                onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                aria-label="Ingrediënt verwijderen"
                className="rounded-lg px-2 py-2 text-sm text-ink-3 transition-colors hover:bg-crit/10 hover:text-crit"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() =>
            setRows((prev) => [...prev, { name: '', quantity: '', unit: '', note: '' }])
          }
          className={secondaryButtonClass}
        >
          + Ingrediënt toevoegen
        </button>
      </section>

      <section className="space-y-3 rounded-2xl border border-edge bg-surface p-5">
        <label className="block">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">
            Bereiding / stappen
          </span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={8}
            className={inputClass}
          />
        </label>
      </section>

      <div className="flex items-center gap-3">
        <button type="submit" disabled={saving} className={primaryButtonClass}>
          {saving ? 'Bezig…' : submitLabel}
        </button>
        {error && <p className="text-sm text-crit">{error}</p>}
      </div>
    </form>
  )
}

function AttributeSelect({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: Attribute[]
  value: number | null
  onChange: (id: number | null) => void
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">{label}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className={inputClass}
      >
        <option value="">—</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function PhotoPreview({ photo }: { photo: PhotoState }) {
  const src =
    photo.kind === 'keep'
      ? photoUrl(photo.path)
      : photo.kind === 'upload'
        ? photo.image.previewUrl
        : photo.kind === 'url' && photo.url.trim() !== ''
          ? photo.url
          : null
  if (!src) return null
  return (
    <img
      src={src}
      alt="Receptfoto"
      className="max-h-56 rounded-xl border border-edge object-cover"
    />
  )
}
