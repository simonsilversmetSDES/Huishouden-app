// Gedeelde helpers voor categorisatieregels (spec §5.3): labels voor de UI en
// een client-side matcher die de backend-engine (services/rules.py) spiegelt.
// Zo kan de importpreview een net toegevoegde regel meteen tonen zonder het
// bestand opnieuw te versturen.

import type { MatchField, MatchType } from '../api/types'

export const FIELD_LABEL: Record<MatchField, string> = {
  counterparty_name: 'Tegenpartij (naam)',
  counterparty_iban: 'Tegenpartij (IBAN)',
  description: 'Omschrijving',
}

export const TYPE_LABEL: Record<MatchType, string> = {
  contains: 'bevat',
  equals: 'is gelijk aan',
  regex: 'regex',
}

export const MATCH_FIELDS = Object.keys(FIELD_LABEL) as MatchField[]
export const MATCH_TYPES = Object.keys(TYPE_LABEL) as MatchType[]

/** Spiegelt normalize_iban in de backend: spaties weg, hoofdletters. */
export function normalizeIban(value: string): string {
  return value.replace(/\s+/g, '').toUpperCase()
}

interface MatchCandidate {
  counterparty_name: string | null
  counterparty_iban: string | null
  description: string | null
}

interface RuleLike {
  match_field: MatchField
  match_type: MatchType
  match_value: string
}

/**
 * True als de regel op de kandidaat matcht. Gelijk aan de backend: contains/
 * equals case-insensitief, regex met IGNORECASE, IBAN op genormaliseerd IBAN,
 * een leeg veld matcht nooit, een kapotte regex matcht nooit.
 */
export function ruleMatches(candidate: MatchCandidate, rule: RuleLike): boolean {
  let value =
    rule.match_field === 'counterparty_name'
      ? candidate.counterparty_name
      : rule.match_field === 'counterparty_iban'
        ? candidate.counterparty_iban
        : candidate.description
  if (!value) return false
  let needle = rule.match_value
  if (rule.match_field === 'counterparty_iban') {
    value = normalizeIban(value)
    if (rule.match_type !== 'regex') needle = normalizeIban(needle)
  }
  switch (rule.match_type) {
    case 'contains':
      return value.toLowerCase().includes(needle.toLowerCase())
    case 'equals':
      return value.toLowerCase() === needle.toLowerCase()
    case 'regex':
      try {
        return new RegExp(needle, 'i').test(value)
      } catch {
        return false
      }
  }
}
