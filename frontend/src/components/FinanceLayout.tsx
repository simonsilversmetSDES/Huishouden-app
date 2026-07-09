import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useAppState } from '../state/AppState'
import {
  IconChartPie,
  IconCoins,
  IconGauge,
  IconGrid,
  IconHome,
  IconReceipt,
  IconTrendingUp,
} from './icons'

const NAV = [
  { to: '/financien', end: true, label: 'Dashboard', icon: IconGauge },
  { to: '/financien/transacties', end: false, label: 'Transacties', icon: IconReceipt },
  { to: '/financien/budget', end: false, label: 'Budget', icon: IconCoins },
  { to: '/financien/vermogen', end: false, label: 'Vermogen', icon: IconChartPie },
  { to: '/financien/beleggingen', end: false, label: 'Beleggingen', icon: IconTrendingUp },
  { to: '/financien/lening', end: false, label: 'Lening', icon: IconHome },
]

export default function FinanceLayout() {
  const { user, logout } = useAuth()
  const { contexts, contextId, setContextId } = useAppState()

  return (
    <div className="min-h-screen bg-page pb-20 text-ink">
      <header className="sticky top-0 z-20 border-b border-edge bg-page/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4">
          <Link
            to="/"
            aria-label="Naar apps"
            className="shrink-0 rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-surface hover:text-ink-2"
          >
            <IconGrid className="size-5" />
          </Link>
          <nav className="flex items-center gap-1 overflow-x-auto">
            {contexts.map((c) => (
              <button
                key={c.id}
                onClick={() => setContextId(c.id)}
                className={`whitespace-nowrap rounded-full px-3 py-1 text-sm transition-colors ${
                  c.id === contextId
                    ? 'bg-ink text-white'
                    : 'text-ink-3 hover:bg-surface hover:text-ink-2'
                }`}
              >
                {c.name}
              </button>
            ))}
          </nav>
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

      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-edge bg-page/95 backdrop-blur">
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
