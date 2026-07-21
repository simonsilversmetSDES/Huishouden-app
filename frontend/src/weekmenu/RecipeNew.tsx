// Nieuw recept: bronkeuze (URL / afbeelding / handmatig) → parse → review-formulier
// → opslaan. De parse slaat nooit iets op; alles is bewerkbaar vóór POST /recipes.

import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createRecipe, parseRecipe } from './api'
import { readDocumentFile } from './documentUpload'
import { readImageFile, type UploadedImage } from './imageUpload'
import RecipeForm, { EMPTY_INITIAL, type FormInitial, type PhotoState } from './RecipeForm'
import type { ParsedRecipe, RecipePayload } from './types'
import { ErrorCard, inputClass, primaryButtonClass } from './ui'
import { useAttributes } from './useAttributes'

type Source = 'url' | 'image' | 'document' | 'manual'

export default function RecipeNew() {
  const navigate = useNavigate()
  const { attributes, error: attrError, reload } = useAttributes()
  const [source, setSource] = useState<Source>('url')
  const [url, setUrl] = useState('')
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)
  // Na parse/bronkeuze: het bewerkbare uitgangspunt voor het formulier.
  const [initial, setInitial] = useState<FormInitial | null>(null)
  const [initialPhoto, setInitialPhoto] = useState<PhotoState>({ kind: 'none' })
  const fileInputRef = useRef<HTMLInputElement>(null)
  const documentInputRef = useRef<HTMLInputElement>(null)

  function toInitial(parsed: ParsedRecipe): FormInitial {
    return {
      title: parsed.title,
      description: parsed.description,
      source_url: parsed.source_url ?? '',
      moment_id: null,
      category_ids: [],
      time_id: null,
      difficulty_id: null,
      servings: parsed.servings,
      ingredients: parsed.ingredients.map((item) => ({
        name: item.name,
        quantity: item.quantity,
        unit: item.unit,
        note: null,
      })),
    }
  }

  async function parseFromUrl() {
    if (url.trim() === '') {
      setParseError('Vul een URL in.')
      return
    }
    setParseError(null)
    setParsing(true)
    try {
      const parsed = await parseRecipe({ url: url.trim() })
      setInitial(toInitial(parsed))
      setInitialPhoto(parsed.photo_url ? { kind: 'url', url: parsed.photo_url } : { kind: 'none' })
    } catch (err) {
      setParseError(err instanceof ApiError ? err.message : 'Recept ophalen mislukt')
    } finally {
      setParsing(false)
    }
  }

  async function parseFromImage(file: File | undefined) {
    if (!file) return
    setParseError(null)
    setParsing(true)
    let image: UploadedImage
    try {
      image = await readImageFile(file)
    } catch (err) {
      setParseError(err instanceof Error ? err.message : 'Afbeelding lezen mislukt')
      setParsing(false)
      return
    }
    try {
      const parsed = await parseRecipe({
        image_base64: image.base64,
        image_media_type: image.mediaType,
      })
      setInitial(toInitial(parsed))
      // De geüploade afbeelding wordt meteen de receptfoto (screenshot-usecase).
      setInitialPhoto({ kind: 'upload', image })
    } catch (err) {
      setParseError(err instanceof ApiError ? err.message : 'Afbeelding parsen mislukt')
    } finally {
      setParsing(false)
    }
  }

  async function parseFromDocument(file: File | undefined) {
    if (!file) return
    setParseError(null)
    setParsing(true)
    try {
      const document = await readDocumentFile(file)
      const parsed = await parseRecipe({
        document_base64: document.base64,
        document_media_type: document.mediaType,
      })
      setInitial(toInitial(parsed))
      // Een Word/PDF-bestand levert geen bruikbare foto.
      setInitialPhoto({ kind: 'none' })
    } catch (err) {
      setParseError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Document parsen mislukt',
      )
    } finally {
      setParsing(false)
    }
  }

  async function save(payload: RecipePayload) {
    const recipe = await createRecipe(payload)
    navigate(`/weekmenu/recepten/${recipe.id}`)
  }

  if (attrError) return <ErrorCard message={attrError} onRetry={reload} />
  if (!attributes) return <p className="py-12 text-center text-sm text-ink-3">Laden…</p>

  if (initial !== null) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setInitial(null)}
            className="text-sm text-ink-3 hover:text-ink-2 hover:underline"
          >
            ← Andere bron
          </button>
          <h1 className="text-lg font-semibold">Recept nakijken</h1>
        </div>
        <RecipeForm
          initial={initial}
          initialPhoto={initialPhoto}
          attributes={attributes}
          submitLabel="Recept opslaan"
          onSubmit={save}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/weekmenu" className="text-sm text-ink-3 hover:text-ink-2 hover:underline">
          ← Recepten
        </Link>
        <h1 className="text-lg font-semibold">Nieuw recept</h1>
      </div>

      <section className="space-y-4 rounded-2xl border border-edge bg-surface p-5">
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ['url', 'Van een website'],
              ['image', 'Van een afbeelding'],
              ['document', 'Van Word/PDF'],
              ['manual', 'Handmatig'],
            ] as [Source, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => {
                setSource(key)
                setParseError(null)
              }}
              className={`rounded-full px-3 py-1 text-sm transition-colors pointer-coarse:py-1.5 ${
                source === key ? 'bg-ink text-white' : 'text-ink-3 hover:bg-raised hover:text-ink-2'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {source === 'url' && (
          <div className="space-y-3">
            <p className="text-sm text-ink-2">
              Plak de link van een receptenpagina; de ingrediënten en stappen worden automatisch
              gelezen.
            </p>
            <div className="flex flex-wrap gap-2">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void parseFromUrl()
                  }
                }}
                placeholder="https://…"
                className={`${inputClass} min-w-52 flex-1`}
              />
              <button onClick={() => void parseFromUrl()} disabled={parsing} className={primaryButtonClass}>
                {parsing ? 'Bezig met lezen…' : 'Recept ophalen'}
              </button>
            </div>
          </div>
        )}

        {source === 'image' && (
          <div className="space-y-3">
            <p className="text-sm text-ink-2">
              Upload een screenshot of foto van een recept (bv. uit Instagram of een kookboek);
              de tekst wordt automatisch gelezen en de afbeelding wordt de receptfoto.
            </p>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={parsing}
              className={primaryButtonClass}
            >
              {parsing ? 'Bezig met lezen…' : 'Kies een afbeelding…'}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                void parseFromImage(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </div>
        )}

        {source === 'document' && (
          <div className="space-y-3">
            <p className="text-sm text-ink-2">
              Upload een Word- (.docx) of PDF-bestand met een recept; de tekst wordt
              automatisch gelezen. Voeg zelf nog een foto toe indien gewenst.
            </p>
            <button
              onClick={() => documentInputRef.current?.click()}
              disabled={parsing}
              className={primaryButtonClass}
            >
              {parsing ? 'Bezig met lezen…' : 'Kies een bestand…'}
            </button>
            <input
              ref={documentInputRef}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              onChange={(e) => {
                void parseFromDocument(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </div>
        )}

        {source === 'manual' && (
          <div className="space-y-3">
            <p className="text-sm text-ink-2">Vul het recept volledig zelf in.</p>
            <button
              onClick={() => {
                setInitial(EMPTY_INITIAL)
                setInitialPhoto({ kind: 'none' })
              }}
              className={primaryButtonClass}
            >
              Leeg formulier openen
            </button>
          </div>
        )}

        {parsing && (
          <p className="text-sm text-ink-3">
            Even geduld — het recept wordt gelezen (dit kan enkele seconden duren)…
          </p>
        )}
        {parseError && <p className="text-sm text-crit">{parseError}</p>}
      </section>
    </div>
  )
}
