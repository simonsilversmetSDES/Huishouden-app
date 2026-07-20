// Gedeelde stijlconstanten + mini-componenten voor de weekmenu-schermen,
// conform de bestaande conventies (lokale inputClass in Rules/Transactions).

export const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm focus:border-accent focus:outline-none'

export const primaryButtonClass =
  'rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50'

export const secondaryButtonClass =
  'rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink-2 transition-colors hover:bg-raised disabled:opacity-50'

/** Neutrale pill (moment/tijd/moeilijkheid). */
export function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-raised px-2.5 py-0.5 text-xs text-ink-2">{children}</span>
  )
}

/** Gekleurde pill (receptcategorie); kleur komt uit de beheerbare tabel. */
export function ColorPill({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span
      className="rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ backgroundColor: `${color}22`, color }}
    >
      {children}
    </span>
  )
}

export function ErrorCard({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-edge bg-surface p-6 text-sm text-ink-2">
      {message}{' '}
      {onRetry && (
        <button onClick={onRetry} className="text-accent hover:underline">
          Opnieuw
        </button>
      )}
    </div>
  )
}
