// Categorisch grafiekpalet, opgebouwd uit de bestaande ramp-swatches (geen nieuwe
// hexes). Gevalideerd met de dataviz-validator (light-mode; de app is light-only):
// lightnessband, chromavloer en contrast ≥ 3:1 slagen; de groen↔oranje CVD-afstand
// valt in de toegestane 8–12-band, wat mag omdat de donut directe labels + gaps
// heeft. Volgorde is vast — categorische tinten worden nooit gecycled.

import type { AssetClass } from '../api/types'

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
}

export const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  contant: 'Contant geld',
  etf_fondsen: "Beleggingsfondsen / ETF's",
  pensioensparen: 'Pensioensparen',
  groepsverzekering: 'Groepsverzekering',
  woning: 'Woning',
  aandelen: 'Aandelen',
}
