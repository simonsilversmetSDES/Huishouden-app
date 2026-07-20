// Layout voor het Weekmenu-gebied, naar model van FinanceLayout (zonder de
// financiën-contextswitcher). Fase 4/5 voegen hier Weekmenu + Boodschappen toe.

import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { IconCalendar, IconGrid, IconSliders, IconUtensils } from '../components/icons'

const NAV = [
  { to: '/weekmenu', end: true, label: 'Recepten', icon: IconUtensils },
  { to: '/weekmenu/week', end: false, label: 'Week', icon: IconCalendar },
  { to: '/weekmenu/beheer', end: false, label: 'Beheer', icon: IconSliders },
]

export default function WeekmenuLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-dvh bg-page pb-[calc(5rem+env(safe-area-inset-bottom))] text-ink">
      <header className="sticky top-0 z-20 border-b border-edge bg-page/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4">
          <Link
            to="/"
            aria-label="Naar apps"
            className="shrink-0 rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-surface hover:text-ink-2"
          >
            <IconGrid className="size-5" />
          </Link>
          <span className="text-sm font-medium text-ink-2">Weekmenu</span>
          <button
            onClick={() => void logout()}
            title={`Ingelogd als ${user?.name ?? ''}`}
            className="ml-auto shrink-0 rounded-lg px-2 py-1.5 text-sm text-ink-3 transition-colors hover:bg-surface hover:text-ink-2"
          >
            Afmelden
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-edge bg-page/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-stretch justify-around px-2">
          {NAV.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] transition-colors ${
                    isActive ? 'text-accent' : 'text-ink-3 hover:text-ink-2'
                  }`
                }
              >
                <Icon className="size-5" />
                {item.label}
              </NavLink>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
