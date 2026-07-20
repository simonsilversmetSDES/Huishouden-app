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

export const IconChartPie = svg(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 3.5V12" />
    <path d="M12 12l6.2 5.8" />
  </>,
)

export const IconTrendingUp = svg(
  <>
    <path d="M3 17l6-6 4 4 8-8" />
    <path d="M17 7h4v4" />
  </>,
)

export const IconHome = svg(
  <>
    <path d="M4 11.5 12 4l8 7.5" />
    <path d="M5.5 10.5V20h13v-9.5" />
    <path d="M10 20v-5h4v5" />
  </>,
)

export const IconPencil = svg(
  <>
    <path d="M4 20l4-1L19 8a2.1 2.1 0 0 0-3-3L5 16z" />
    <path d="M14.5 6.5l3 3" />
  </>,
)

export const IconSliders = svg(
  <>
    <path d="M4 7h9M17 7h3" />
    <circle cx="15" cy="7" r="2" />
    <path d="M4 17h3M11 17h9" />
    <circle cx="9" cy="17" r="2" />
  </>,
)

export const IconPlus = svg(
  <>
    <path d="M12 5v14M5 12h14" />
  </>,
)

export const IconTrash = svg(
  <>
    <path d="M4 6.5h16" />
    <path d="M9.5 6.5V4.8c0-.7.6-1.3 1.3-1.3h2.4c.7 0 1.3.6 1.3 1.3v1.7" />
    <path d="M6.5 6.5l1 13c.1.8.7 1.5 1.5 1.5h6c.8 0 1.4-.7 1.5-1.5l1-13" />
    <path d="M10 10.5v6M14 10.5v6" />
  </>,
)

export const IconCalendar = svg(
  <>
    <rect x="3.5" y="5" width="17" height="15" rx="2" />
    <path d="M3.5 9.5h17" />
    <path d="M8 3v4M16 3v4" />
  </>,
)
