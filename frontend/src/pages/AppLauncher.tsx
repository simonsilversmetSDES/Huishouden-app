import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { IconListChecks, IconUtensils, IconWallet } from '../components/icons'

interface AppCard {
  to: string
  title: string
  subtitle: string
  icon: (props: { className?: string }) => React.ReactNode
  tint: string // achtergrond + tekstkleur via role-tokens
}

const APPS: AppCard[] = [
  {
    to: '/financien',
    title: 'Financiën',
    subtitle: 'Budget, transacties, vermogen & beleggingen',
    icon: IconWallet,
    tint: 'bg-saving/10 text-saving',
  },
  {
    to: '/lijstjes',
    title: 'Lijstjes',
    subtitle: "Boodschappen, to-do's & cadeau-ideeën",
    icon: IconListChecks,
    tint: 'bg-income/10 text-income',
  },
  {
    to: '/weekmenu',
    title: 'Weekmenu',
    subtitle: 'Gerechten, planning & boodschappen',
    icon: IconUtensils,
    tint: 'bg-expense/10 text-expense',
  },
]

export default function AppLauncher() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-dvh bg-page text-ink">
      <header className="sticky top-0 z-20 border-b border-edge bg-page/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-4xl items-center px-4">
          <span className="text-[15px] font-semibold tracking-tight">Huishouden</span>
          <button
            onClick={() => void logout()}
            title={`Ingelogd als ${user?.name ?? ''}`}
            className="ml-auto rounded-lg px-2 py-1.5 text-sm text-ink-3 transition-colors hover:bg-surface hover:text-ink-2"
          >
            Afmelden
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-10">
        <h1 className="text-3xl font-semibold tracking-tight">Welkom terug</h1>
        <p className="mt-1 text-ink-3">Kies een app om verder te gaan.</p>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {APPS.map((app) => {
            const Icon = app.icon
            return (
              <Link
                key={app.to}
                to={app.to}
                className="group flex items-center gap-4 rounded-2xl border border-edge bg-surface p-5 transition-colors hover:bg-raised/50"
              >
                <span className={`flex size-12 shrink-0 items-center justify-center rounded-xl ${app.tint}`}>
                  <Icon className="size-6" />
                </span>
                <span className="min-w-0">
                  <span className="block text-lg font-semibold">{app.title}</span>
                  <span className="block truncate text-sm text-ink-3">{app.subtitle}</span>
                </span>
              </Link>
            )
          })}
        </div>
      </main>
    </div>
  )
}
