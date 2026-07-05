// Gedeelde app-state: de contextenlijst en de gekozen context (Gem./Simon/Jozefien).
// De keuze blijft bewaard in localStorage zodat elke pagina dezelfde context toont.

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api/client'
import type { Context } from '../api/types'

const STORAGE_KEY = 'huishouden.contextId'

interface AppState {
  contexts: Context[]
  contextId: number | null
  setContextId: (id: number) => void
}

const AppStateContext = createContext<AppState | null>(null)

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [contexts, setContexts] = useState<Context[]>([])
  const [contextId, setContextIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? Number(stored) : null
  })

  useEffect(() => {
    api<Context[]>('/api/contexts')
      .then((list) => {
        setContexts(list)
        setContextIdState((current) =>
          current !== null && list.some((c) => c.id === current)
            ? current
            : (list[0]?.id ?? null),
        )
      })
      .catch(() => setContexts([]))
  }, [])

  const value = useMemo<AppState>(
    () => ({
      contexts,
      contextId,
      setContextId: (id: number) => {
        localStorage.setItem(STORAGE_KEY, String(id))
        setContextIdState(id)
      },
    }),
    [contexts, contextId],
  )

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext)
  if (!ctx) throw new Error('useAppState moet binnen <AppStateProvider> gebruikt worden')
  return ctx
}
