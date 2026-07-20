// Lineair herberekenen van ingrediënt-hoeveelheden bij een ander aantal personen.
// Werkt op de quantity-strings die parsing.py opslaat (zie _INGREDIENT_RE aldaar):
// een los getal ("500", "1,5"), een unicode-breuk ("½", "¼", "¾"), of twee getallen met
// een scheidingsteken ("1/2", "2-3"). "/" betekent een breuk (1 gedeeld door 2, dus
// schalen als decimaal); "-"/"–" betekent een range (bv. "2-3 tomaten") — beide kanten
// apart schalen en weer samenvoegen. Niet-numerieke hoeveelheden ("snufje") blijven
// ongewijzigd; dat kan de app niet zinvol schalen.

const UNICODE_FRACTIONS: Record<string, number> = { '½': 0.5, '¼': 0.25, '¾': 0.75 }

function parseNumber(token: string): number | null {
  if (token in UNICODE_FRACTIONS) return UNICODE_FRACTIONS[token]
  const normalized = token.replace(',', '.')
  const value = Number(normalized)
  return Number.isFinite(value) ? value : null
}

function formatNumber(value: number): string {
  const rounded = Math.round(value * 100) / 100
  return rounded.toString().replace('.', ',')
}

export function scaleQuantity(quantity: string | null, factor: number): string | null {
  if (quantity === null || factor === 1) return quantity
  const trimmed = quantity.trim()

  const fractionMatch = trimmed.match(/^(.+?)\s*\/\s*(.+)$/)
  if (fractionMatch) {
    const numerator = parseNumber(fractionMatch[1])
    const denominator = parseNumber(fractionMatch[2])
    if (numerator !== null && denominator !== null && denominator !== 0) {
      return formatNumber((numerator / denominator) * factor)
    }
  }

  const rangeMatch = trimmed.match(/^(.+?)\s*[-–]\s*(.+)$/)
  if (rangeMatch) {
    const from = parseNumber(rangeMatch[1])
    const to = parseNumber(rangeMatch[2])
    if (from !== null && to !== null) {
      return `${formatNumber(from * factor)}-${formatNumber(to * factor)}`
    }
  }

  const single = parseNumber(trimmed)
  if (single !== null) return formatNumber(single * factor)

  return quantity
}
