// Kleine inline-SVG-iconen (currentColor, 24×24) voor de app-launcher en de
// financiën-navigatie. Geen externe icon-library — houdt de bundel licht en de
// stijl consistent met het lichte Excel-thema.

type IconProps = { className?: string }

function svg(children: React.ReactNode) {
  return function Icon({ className }: IconProps) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden
      >
        {children}
      </svg>
    )
  }
}

export const IconGrid = svg(
  <>
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
  </>,
)

export const IconWallet = svg(
  <>
    <rect x="3" y="6" width="18" height="13" rx="2.5" />
    <path d="M3 10h18" />
    <circle cx="16.5" cy="14.5" r="1.2" />
  </>,
)

export const IconListChecks = svg(
  <>
    <path d="M11 6h9M11 12h9M11 18h9" />
    <path d="M3.5 6l1.5 1.5L7.5 4" />
    <path d="M3.5 12l1.5 1.5L7.5 10" />
    <path d="M3.5 18l1.5 1.5L7.5 16" />
  </>,
)

export const IconUtensils = svg(
  <>
    <path d="M7 3v18" />
    <path d="M4.5 3v5a2.5 2.5 0 005 0V3" />
    <path d="M17.5 3c-1.6 0-2.8 1.8-2.8 5s1.2 4 2.8 4v9" />
  </>,
)

export const IconGauge = svg(
  <>
    <path d="M4 19a8 8 0 1116 0" />
    <path d="M12 15l3.5-4" />
  </>,
)

export const IconReceipt = svg(
  <>
    <path d="M6 3h12v18l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4L6 21z" />
    <path d="M9 8h6M9 12h6" />
  </>,
)

export const IconCoins = svg(
  <>
    <ellipse cx="9" cy="7" rx="5" ry="2.5" />
    <path d="M4 7v4c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5V7" />
    <path d="M10 15.5c.6 1.2 2.6 2 5 2 2.8 0 5-1.1 5-2.5v-4c0-1-1.1-1.9-3-2.3" />
  </>,
)

export const IconBank = svg(
  <>
    <path d="M4 21h16" />
    <path d="M5 21V10l7-5 7 5v11" />
    <path d="M9.5 21v-6h5v6" />
  </>,
)

export const IconTrendingUp = svg(
  <>
    <path d="M3 17l6-6 4 4 8-8" />
    <path d="M17 7h4v4" />
  </>,
)
