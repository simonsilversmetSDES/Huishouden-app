import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useAppState } from '../state/AppState'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm transition-colors ${
    isActive ? 'bg-surface text-ink' : 'text-ink-3 hover:bg-surface/60 hover:text-ink-2'
  }`

export default function AppShell() {
  const { user, logout } = useAuth()
  const { contexts, contextId, setContextId } = useAppState()

  return (
    <div className="min-h-screen bg-page text-ink">
      <header className="sticky top-0 z-20 border-b border-edge bg-page/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-4">
          <span className="mr-1 text-[15px] font-semibold tracking-tight sm:mr-2">
            Huishouden
          </span>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navLinkClass}>
              Dashboard
            </NavLink>
            <NavLink to="/budget" className={navLinkClass}>
              Budget
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <select
              value={contextId ?? ''}
              onChange={(e) => setContextId(Number(e.target.value))}
              aria-label="Context"
              className="rounded-lg border border-edge bg-surface px-2 py-1.5 text-sm text-ink-2 focus:border-accent focus:outline-none"
            >
              {contexts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button
              onClick={() => void logout()}
              title={`Ingelogd als ${user?.name ?? ''}`}
              className="rounded-lg px-2 py-1.5 text-sm text-ink-3 transition-colors hover:bg-surface/60 hover:text-ink-2"
            >
              Uitloggen
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
