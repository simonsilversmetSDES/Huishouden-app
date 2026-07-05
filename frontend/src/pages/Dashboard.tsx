import { useAuth } from '../auth/AuthContext'

export default function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex items-center justify-between bg-white px-6 py-4 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-800">Huishouden</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-600">Hallo, {user?.name}</span>
          <button
            onClick={() => void logout()}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Uitloggen
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-10">
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <h2 className="text-xl font-medium text-slate-700">Dashboard komt eraan</h2>
          <p className="mt-2 text-sm text-slate-500">
            Fase 1 is het fundament: inloggen werkt, de database staat klaar. De modules
            (budget, transacties, beleggingen, lening, balans) volgen in de volgende fases.
          </p>
        </div>
      </main>
    </div>
  )
}
