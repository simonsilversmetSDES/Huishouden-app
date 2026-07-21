// Beheerscherm: tabs voor de vijf attribuuttabellen + het ingrediëntenbeheer.

import { useState } from 'react'
import AttributeManager from './AttributeManager'
import type { AttributePath } from './api'
import IngredientManager from './IngredientManager'

type Tab = AttributePath | 'ingredients'

const TABS: { key: Tab; label: string }[] = [
  { key: 'moments', label: 'Momenten' },
  { key: 'categories', label: 'Categorieën' },
  { key: 'times', label: 'Tijd' },
  { key: 'difficulties', label: 'Moeilijkheid' },
  { key: 'shopping-categories', label: 'Winkelcategorieën' },
  { key: 'ingredients', label: 'Ingrediënten' },
]

const HAS_COLOR: Partial<Record<Tab, boolean>> = {
  categories: true,
  'shopping-categories': true,
}

export default function Beheer() {
  const [tab, setTab] = useState<Tab>('moments')

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Beheer</h1>

      <div className="scrollbar-none flex gap-1.5 overflow-x-auto overscroll-x-contain">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`whitespace-nowrap rounded-full px-3 py-1 text-sm transition-colors pointer-coarse:py-1.5 ${
              tab === t.key ? 'bg-ink text-white' : 'text-ink-3 hover:bg-surface hover:text-ink-2'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'ingredients' ? (
        <IngredientManager />
      ) : (
        <AttributeManager key={tab} path={tab} hasColor={HAS_COLOR[tab] ?? false} />
      )}
    </div>
  )
}
