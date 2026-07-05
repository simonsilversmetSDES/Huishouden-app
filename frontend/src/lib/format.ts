// nl-BE-weergave (CLAUDE.md): bedragen als € 1.234,56 en datums als dd/mm/jjjj.
// Bedragen komen van de API als integer-centen — nooit als float rekenen.

const euro = new Intl.NumberFormat('nl-BE', {
  style: 'currency',
  currency: 'EUR',
})

const datum = new Intl.DateTimeFormat('nl-BE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

/** Formatteert integer-centen als "€ 1.234,56". */
export function formatCents(cents: number): string {
  return euro.format(cents / 100)
}

/** Formatteert een ISO-datum ("2026-07-05") als "05/07/2026". */
export function formatDate(isoDate: string): string {
  return datum.format(new Date(isoDate))
}
