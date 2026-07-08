// Categorisch grafiekpalet, opgebouwd uit de bestaande ramp-swatches (geen nieuwe
// hexes). Gevalideerd met de dataviz-validator (light-mode; de app is light-only):
// lightnessband, chromavloer en contrast ≥ 3:1 slagen; de groen↔oranje CVD-afstand
// valt in de toegestane 8–12-band, wat mag omdat de donut directe labels + gaps
// heeft. Volgorde is vast — categorische tinten worden nooit gecycled.

import type { AssetClass } from '../api/types'

// Sequentiële tinten per type (donkerste = grootste), zoals de Excel-donuts.
// Gedeeld door DonutCard en de vermogens-donut.
export const RAMPS: Record<'income' | 'expense' | 'saving', string[]> = {
  income: ['#025402', '#068006', '#2fa32f', '#66c266', '#a3dba3'],
  expense: ['#8f3113', '#c24a1f', '#eb6834', '#f29a72', '#f8ccb3'],
  saving: ['#123f73', '#1d5aa6', '#2a78d6', '#6ba3e4', '#b3cff2'],
}
export const OTHER_HEX = '#d5d4cc'

export const CATEGORICAL = [
  '#1d5aa6', // blauw
  '#eb6834', // oranje
  '#068006', // groen
  '#2a78d6', // lichter blauw
  '#c24a1f', // donker oranje
  '#2fa32f', // lichter groen
]

/** Kleur per reeks-index (bv. per rekening). Nooit cyclen: valt terug op neutraal. */
export function seriesColor(index: number): string {
  return CATEGORICAL[index] ?? '#898781'
}

// Vaste kleur per activaklasse (kleur volgt de entiteit, niet de rang).
export const ASSET_CLASS_COLORS: Record<AssetClass, string> = {
  contant: '#1d5aa6',
  etf_fondsen: '#eb6834',
  pensioensparen: '#068006',
  groepsverzekering: '#2a78d6',
  woning: '#c24a1f',
  aandelen: '#2fa32f',
  bitcoin: '#f7931a',
}

export const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  contant: 'Contant geld',
  etf_fondsen: "Beleggingsfondsen / ETF's",
  pensioensparen: 'Pensioensparen',
  groepsverzekering: 'Groepsverzekering',
  woning: 'Woning',
  aandelen: 'Aandelen',
  bitcoin: 'Bitcoin',
}
