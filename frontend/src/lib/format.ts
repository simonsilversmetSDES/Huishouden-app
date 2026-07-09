// nl-BE-weergave (CLAUDE.md): bedragen als € 1.234,56 en datums als dd/mm/jjjj.
// Bedragen komen van de API als integer-centen — nooit als float rekenen.

const euro = new Intl.NumberFormat('nl-BE', {
  style: 'currency',
  currency: 'EUR',
})

const plain = new Intl.NumberFormat('nl-BE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const plainWhole = new Intl.NumberFormat('nl-BE', {
  maximumFractionDigits: 0,
})

const datum = new Intl.DateTimeFormat('nl-BE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const maandJaar = new Intl.DateTimeFormat('nl-BE', { month: 'long', year: 'numeric' })

export const MAAND_KORT = [
  'jan',
  'feb',
  'mrt',
  'apr',
  'mei',
  'jun',
  'jul',
  'aug',
  'sep',
  'okt',
  'nov',
  'dec',
]

/** Formatteert integer-centen als "€ 1.234,56". */
export function formatCents(cents: number): string {
  return euro.format(cents / 100)
}

/** Formatteert integer-centen als "1.234,56" (zonder €-teken, voor tabelcellen). */
export function formatCentsPlain(cents: number): string {
  return plain.format(cents / 100)
}

/** Formatteert integer-centen als "1.234" — afgerond op hele euro's, geen decimalen
 * (voor de budgetmatrix). */
export function formatCentsWhole(cents: number): string {
  return plainWhole.format(Math.round(cents / 100))
}

/** Formatteert een ISO-datum ("2026-07-05") als "05/07/2026". */
export function formatDate(isoDate: string): string {
  return datum.format(new Date(isoDate))
}

/** "juli 2026" voor een jaar/maand-combinatie. */
export function formatMonthYear(year: number, month: number): string {
  return maandJaar.format(new Date(year, month - 1, 1))
}

/**
 * Parseert gebruikersinvoer ("1.234,56", "1234,56", "1234.56", "1234") naar
 * integer-centen, via string-bewerking — nooit via float. Ongeldig → null.
 */
export function parseEuroToCents(input: string): number | null {
  let text = input.trim().replace(/[€\s]/g, '')
  if (text === '') return 0
  let negative = false
  if (text.startsWith('-')) {
    negative = true
    text = text.slice(1)
  }
  let integerPart: string
  let decimalPart: string
  if (text.includes(',')) {
    // komma = decimaalteken; punten zijn duizendtallen
    const [head, tail, ...rest] = text.split(',')
    if (rest.length > 0) return null
    integerPart = head.replace(/\./g, '')
    decimalPart = tail
  } else if (text.includes('.')) {
    // enkel punt(en): 1 punt met ≤2 decimalen = decimaalteken, anders duizendtallen
    const parts = text.split('.')
    if (parts.length === 2 && parts[1].length <= 2) {
      integerPart = parts[0]
      decimalPart = parts[1]
    } else {
      integerPart = parts.join('')
      decimalPart = ''
    }
  } else {
    integerPart = text
    decimalPart = ''
  }
  if (integerPart === '') integerPart = '0'
  decimalPart = (decimalPart + '00').slice(0, 2)
  if (!/^\d+$/.test(integerPart) || !/^\d{2}$/.test(decimalPart)) return null
  const cents = parseInt(integerPart, 10) * 100 + parseInt(decimalPart, 10)
  return negative ? -cents : cents
}
