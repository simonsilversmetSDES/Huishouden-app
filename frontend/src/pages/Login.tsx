import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ApiError, useAuth } from '../auth/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      const from = (location.state as { from?: string } | null)?.from ?? '/'
      navigate(from, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'Ongeldige inloggegevens'
          : 'Er ging iets mis — probeer opnieuw',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-page px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-2xl border border-edge bg-surface p-8"
      >
        <h1 className="text-2xl font-semibold tracking-tight">Huishouden</h1>
        <p className="text-sm text-ink-3">Log in om verder te gaan.</p>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink-2">E-mailadres</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-edge bg-page px-3 py-2 focus:border-accent focus:outline-none"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink-2">Wachtwoord</span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-edge bg-page px-3 py-2 focus:border-accent focus:outline-none"
          />
        </label>

        {error && <p className="text-sm text-crit">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-accent py-2 font-medium text-white transition-colors hover:bg-accent/85 disabled:opacity-50"
        >
          {busy ? 'Bezig…' : 'Inloggen'}
        </button>
      </form>
    </main>
  )
}
