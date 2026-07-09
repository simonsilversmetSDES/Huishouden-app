import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type {
  Category,
  Context,
  MatchField,
  MatchType,
  Rule,
  RuleApplyResult,
  RulePayload,
} from '../api/types'
import CategoryPicker from '../components/CategoryPicker'
import { FIELD_LABEL, MATCH_FIELDS, MATCH_TYPES, TYPE_LABEL } from '../lib/rules'
import { useAppState } from '../state/AppState'

const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'

export default function Rules() {
  const { contextId, contexts } = useAppState()
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [editing, setEditing] = useState<Rule | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applyMsg, setApplyMsg] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const formRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (contextId === null) return
    api<Category[]>(`/api/categories?context_id=${contextId}`)
      .then(setCategories)
      .catch(() => setCategories([]))
  }, [contextId])

  const load = useCallback(() => {
    if (contextId === null) return
    setError(null)
    api<Rule[]>(`/api/rules?context_id=${contextId}`)
      .then(setRules)
      .catch(() => setError('Regels laden mislukt — probeer opnieuw'))
  }, [contextId])

  useEffect(load, [load])

  if (contextId === null) return null

  function startEdit(rule: Rule) {
    setEditing(rule)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function remove(rule: Rule) {
    if (!window.confirm(`Regel "${rule.match_value}" → ${rule.category_name} verwijderen?`)) {
      return
    }
    try {
      await api<void>(`/api/rules/${rule.id}`, { method: 'DELETE' })
      if (editing?.id === rule.id) setEditing(null)
      load()
    } catch {
      setError('Verwijderen mislukt — probeer opnieuw')
    }
  }

  const [togglingId, setTogglingId] = useState<number | null>(null)

  // Badge-klik in de tabel: entiteit aan/uit zetten zonder het bewerkformulier.
  async function toggleContext(rule: Rule, ctxId: number) {
    const has = rule.context_ids.includes(ctxId)
    if (has && rule.context_ids.length === 1) return // minstens één entiteit
    const next = has
      ? rule.context_ids.filter((id) => id !== ctxId)
      : [...rule.context_ids, ctxId]
    const payload: RulePayload = {
      context_id: rule.context_id,
      match_field: rule.match_field,
      match_type: rule.match_type,
      match_value: rule.match_value,
      category_id: rule.category_id,
      priority: rule.priority,
      created_from_correction: rule.created_from_correction,
      context_ids: next,
    }
    setTogglingId(rule.id)
    try {
      await api<Rule>(`/api/rules/${rule.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      load()
    } catch {
      setError('Entiteit wijzigen mislukt — probeer opnieuw')
    } finally {
      setTogglingId(null)
    }
  }

  async function apply() {
    setApplyMsg(null)
    setApplying(true)
    try {
      const res = await api<RuleApplyResult>(`/api/rules/apply?context_id=${contextId}`, {
        method: 'POST',
      })
      setApplyMsg(
        res.updated_count === 0
          ? 'Geen ongecategoriseerde transacties bijgewerkt.'
          : `${res.updated_count} transactie${res.updated_count === 1 ? '' : 's'} bijgewerkt.`,
      )
    } catch {
      setApplyMsg('Toepassen mislukt — probeer opnieuw')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Categorisatieregels</h1>
        <div className="ml-auto flex items-center gap-3">
          {applyMsg && <span className="text-sm text-ink-3">{applyMsg}</span>}
          <button
            onClick={() => void apply()}
            disabled={applying}
            className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 transition-colors hover:bg-raised disabled:opacity-50"
          >
            {applying ? 'Bezig…' : 'Regels toepassen'}
          </button>
        </div>
      </div>

      <RuleForm
        ref={formRef}
        contextId={contextId}
        contexts={contexts}
        categories={categories}
        editing={editing}
        onCancelEdit={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          load()
        }}
      />

      {error && (
        <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
          {error}{' '}
          <button onClick={load} className="text-accent hover:underline">
            Opnieuw
          </button>
        </div>
      )}

      {!error && (
        <section className="overflow-x-auto rounded-2xl border border-edge bg-surface">
          {rules === null ? (
            <p className="py-12 text-center text-sm text-ink-3">Laden…</p>
          ) : rules.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-ink-2">
              Nog geen regels voor deze context.
            </p>
          ) : (
            <RuleTable
              rules={rules}
              contexts={contexts}
              togglingId={togglingId}
              onToggleContext={(rule, ctxId) => void toggleContext(rule, ctxId)}
              onEdit={startEdit}
              onDelete={remove}
            />
          )}
        </section>
      )}
    </div>
  )
}

function RuleForm({
  ref,
  contextId,
  contexts,
  categories,
  editing,
  onCancelEdit,
  onSaved,
}: {
  ref: React.RefObject<HTMLElement | null>
  contextId: number
  contexts: Context[]
  categories: Category[]
  editing: Rule | null
  onCancelEdit: () => void
  onSaved: () => void
}) {
  const [matchField, setMatchField] = useState<MatchField>('counterparty_name')
  const [matchType, setMatchType] = useState<MatchType>('contains')
  const [matchValue, setMatchValue] = useState('')
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [priority, setPriority] = useState('100')
  const [contextIds, setContextIds] = useState<number[]>([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => setCategoryId(''), [contextId])

  // Nieuwe regel: standaard alle entiteiten aangevinkt (#9).
  useEffect(() => {
    if (editing === null) setContextIds(contexts.map((c) => c.id))
  }, [contexts, editing])

  useEffect(() => {
    if (editing === null) return
    setMatchField(editing.match_field)
    setMatchType(editing.match_type)
    setMatchValue(editing.match_value)
    setCategoryId(editing.category_id)
    setPriority(String(editing.priority))
    setContextIds(editing.context_ids)
    setSaveError(null)
  }, [editing])

  function toggleCtx(id: number) {
    setContextIds((prev) =>
      prev.includes(id)
        ? prev.length === 1
          ? prev
          : prev.filter((x) => x !== id)
        : [...prev, id],
    )
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (matchValue.trim() === '' || categoryId === '') {
      setSaveError('Matchwaarde en categorie zijn verplicht')
      return
    }
    setSaveError(null)
    setSaving(true)
    const payload: RulePayload = {
      context_id: contextId,
      match_field: matchField,
      match_type: matchType,
      match_value: matchValue.trim(),
      category_id: categoryId,
      priority: Number(priority) || 0,
      created_from_correction: editing?.created_from_correction ?? false,
      context_ids: contextIds,
    }
    try {
      if (editing) {
        await api<Rule>(`/api/rules/${editing.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      } else {
        await api<Rule>('/api/rules', { method: 'POST', body: JSON.stringify(payload) })
      }
      setMatchValue('')
      setCategoryId('')
      onSaved()
    } catch (err) {
      setSaveError(
        err instanceof ApiError ? err.message : 'Opslaan mislukt — probeer opnieuw',
      )
    } finally {
      setSaving(false)
    }
  }

  function cancelEdit() {
    setMatchValue('')
    setCategoryId('')
    setSaveError(null)
    onCancelEdit()
  }

  return (
    <section ref={ref} className="rounded-2xl border border-edge bg-surface p-5">
      <h2 className="text-sm font-medium">{editing ? 'Regel bewerken' : 'Regel toevoegen'}</h2>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="block lg:col-span-1">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Veld</span>
          <select
            value={matchField}
            onChange={(e) => setMatchField(e.target.value as MatchField)}
            className={inputClass}
          >
            {MATCH_FIELDS.map((f) => (
              <option key={f} value={f}>
                {FIELD_LABEL[f]}
              </option>
            ))}
          </select>
        </label>
        <label className="block lg:col-span-1">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Match</span>
          <select
            value={matchType}
            onChange={(e) => setMatchType(e.target.value as MatchType)}
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
            type="text"
            value={matchValue}
            onChange={(e) => setMatchValue(e.target.value)}
            placeholder={matchType === 'regex' ? 'bv. mobile\\s+vikings' : 'bv. COLRUYT'}
            className={inputClass}
          />
        </label>
        <label className="block lg:col-span-1">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Categorie</span>
          <CategoryPicker
            categories={categories}
            value={categoryId === '' ? null : categoryId}
            onChange={(id) => setCategoryId(id ?? '')}
            groupByType
            placeholder="— kies —"
            ariaLabel="Categorie"
            className={inputClass}
          />
        </label>
        <label className="block lg:col-span-1">
          <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Prioriteit</span>
          <input
            type="number"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className={`${inputClass} text-right tabular-nums`}
          />
        </label>
        {contexts.length > 1 && (
          <div className="sm:col-span-2 lg:col-span-6">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-3">Geldt voor</span>
            <div className="flex flex-wrap gap-4">
              {contexts.map((c) => (
                <label key={c.id} className="flex items-center gap-1.5 text-sm text-ink-2">
                  <input
                    type="checkbox"
                    checked={contextIds.includes(c.id)}
                    onChange={() => toggleCtx(c.id)}
                    className="size-4 accent-accent"
                  />
                  {c.name}
                </label>
              ))}
            </div>
          </div>
        )}
        <div className="flex items-center gap-3 sm:col-span-2 lg:col-span-6">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
          >
            {editing ? 'Opslaan' : 'Toevoegen'}
          </button>
          {editing && (
            <button
              type="button"
              onClick={cancelEdit}
              className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 hover:bg-raised"
            >
              Annuleren
            </button>
          )}
          {saveError && <p className="text-sm text-crit">{saveError}</p>}
        </div>
      </form>
      <p className="mt-3 text-xs text-ink-3">
        Regels worden op prioriteit geëvalueerd (laagste eerst); de eerste match wint.
      </p>
    </section>
  )
}

function RuleTable({
  rules,
  contexts,
  togglingId,
  onToggleContext,
  onEdit,
  onDelete,
}: {
  rules: Rule[]
  contexts: Context[]
  togglingId: number | null
  onToggleContext: (rule: Rule, ctxId: number) => void
  onEdit: (rule: Rule) => void
  onDelete: (rule: Rule) => void
}) {
  const showEntities = contexts.length > 1
  return (
    <table className="w-full min-w-[720px] text-sm">
      <thead>
        <tr className="border-b border-line text-xs text-ink-3">
          <th className="px-5 py-3 text-right font-medium">Prio</th>
          <th className="px-3 py-3 text-left font-medium">Veld</th>
          <th className="px-3 py-3 text-left font-medium">Match</th>
          <th className="px-3 py-3 text-left font-medium">Waarde</th>
          <th className="px-3 py-3 text-left font-medium">Categorie</th>
          {showEntities && <th className="px-3 py-3 text-left font-medium">Geldt voor</th>}
          <th className="px-5 py-3" />
        </tr>
      </thead>
      <tbody>
        {rules.map((rule) => (
          <tr key={rule.id} className="border-b border-line last:border-b-0 hover:bg-raised/50">
            <td className="px-5 py-2 text-right tabular-nums text-ink-3">{rule.priority}</td>
            <td className="whitespace-nowrap px-3 py-2">{FIELD_LABEL[rule.match_field]}</td>
            <td className="whitespace-nowrap px-3 py-2 text-ink-2">{TYPE_LABEL[rule.match_type]}</td>
            <td className="px-3 py-2 font-medium">{rule.match_value}</td>
            <td className="px-3 py-2">
              {rule.category_name ?? <span className="text-ink-3">–</span>}
              {rule.created_from_correction && (
                <span className="ml-2 rounded-md bg-raised px-1.5 py-0.5 text-[11px] text-ink-3">
                  uit correctie
                </span>
              )}
            </td>
            {showEntities && (
              <td className="px-3 py-2">
                <span className="flex flex-wrap gap-1">
                  {contexts.map((c) => (
                    <ContextBadge
                      key={c.id}
                      rule={rule}
                      context={c}
                      busy={togglingId === rule.id}
                      onToggle={() => onToggleContext(rule, c.id)}
                    />
                  ))}
                </span>
              </td>
            )}
            <td className="whitespace-nowrap px-5 py-2 text-right">
              <button
                onClick={() => onEdit(rule)}
                className="text-xs text-ink-3 hover:text-ink-2 hover:underline"
              >
                Bewerken
              </button>
              <button
                onClick={() => onDelete(rule)}
                className="ml-3 text-xs text-ink-3 hover:text-crit hover:underline"
              >
                Verwijderen
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Klikbare 'geldt voor'-badge: aan = vol, uit = gestippeld/licht (klik zet aan),
 * niet-toepasbaar (categorie bestaat er niet actief) = uitgegrijsd en niet klikbaar. */
function ContextBadge({
  rule,
  context,
  busy,
  onToggle,
}: {
  rule: Rule
  context: Context
  busy: boolean
  onToggle: () => void
}) {
  const applicable = rule.applicable_context_ids.includes(context.id)
  const on = rule.context_ids.includes(context.id)
  const lastOne = on && rule.context_ids.length === 1

  if (!applicable) {
    return (
      <span
        title={`Categorie "${rule.category_name ?? '?'}" bestaat niet (actief) bij ${context.name}`}
        className="cursor-not-allowed rounded-md border border-dashed border-line px-1.5 py-0.5 text-[11px] text-ink-3 opacity-40"
      >
        {context.name}
      </span>
    )
  }
  return (
    <button
      onClick={onToggle}
      disabled={busy || lastOne}
      title={
        lastOne
          ? 'Minstens één entiteit vereist'
          : on
            ? `Klik om uit te schakelen bij ${context.name}`
            : `Klik om in te schakelen bij ${context.name}`
      }
      className={`rounded-md px-1.5 py-0.5 text-[11px] transition-colors disabled:cursor-default ${
        on
          ? 'border border-transparent bg-raised text-ink-2 hover:bg-accent/15'
          : 'border border-dashed border-edge text-ink-3 opacity-60 hover:border-accent hover:text-accent hover:opacity-100'
      } ${busy ? 'opacity-40' : ''}`}
    >
      {context.name}
    </button>
  )
}
