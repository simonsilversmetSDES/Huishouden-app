import { Link } from 'react-router-dom'
import { IconGrid } from '../components/icons'

export default function ComingSoon({ title }: { title: string }) {
  return (
    <div className="min-h-screen bg-page text-ink">
      <header className="sticky top-0 z-20 border-b border-edge bg-page/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-4xl items-center gap-2 px-4">
          <Link
            to="/"
            aria-label="Naar apps"
            className="rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-surface hover:text-ink-2"
          >
            <IconGrid className="size-5" />
          </Link>
          <span className="text-[15px] font-semibold tracking-tight">{title}</span>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-24 text-center">
        <p className="text-lg font-medium">Binnenkort beschikbaar</p>
        <p className="mt-2 text-sm text-ink-3">
          Deze app is nog in ontwikkeling.{' '}
          <Link to="/" className="text-accent hover:underline">
            Terug naar de apps
          </Link>
        </p>
      </main>
    </div>
  )
}
