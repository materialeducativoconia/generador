import { useState } from 'react'

/* Prices in Mexican pesos or US dollars (backend app/plans.py PRICE_MXN): many Mexican cards decline a charge in
 * dollars, so Stripe charges in the currency picked here. Pesos by default in Mexico (the browser's time zone or
 * language); the choice is remembered, also across the Google sign-in that leads to Stripe. */
export type Currency = 'mxn' | 'usd'
const KEY = 'currency'
const MEXICO = /^America\/(Mexico_City|Monterrey|Merida|Cancun|Chihuahua|Ciudad_Juarez|Hermosillo|Mazatlan|Tijuana|Matamoros|Ojinaga|Bahia_Banderas)$/

export function defaultCurrency(): Currency {
  try {
    const kept = localStorage.getItem(KEY)
    if (kept === 'mxn' || kept === 'usd') return kept
  } catch { /* private window */ }
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone ?? ''
  return MEXICO.test(zone) || navigator.language?.toLowerCase() === 'es-mx' ? 'mxn' : 'usd'
}

export function useCurrency(): [Currency, (c: Currency) => void] {
  const [currency, set] = useState<Currency>(defaultCurrency)
  return [currency, (c) => { set(c); try { localStorage.setItem(KEY, c) } catch { /* private window */ } }]
}

export const money = (p: { price_usd: number; price_mxn: number }, c: Currency) =>
  c === 'mxn' ? `$${p.price_mxn.toLocaleString('es-MX')} MXN` : `$${p.price_usd} USD`

export function CurrencyToggle({ currency, onChange }: { currency: Currency; onChange: (c: Currency) => void }) {
  return (
    <div className="segmented currency-toggle" role="radiogroup" aria-label="Moneda">
      {(['mxn', 'usd'] as const).map((c) => (
        <button key={c} type="button" role="radio" aria-checked={currency === c} className={currency === c ? 'on' : ''} onClick={() => onChange(c)}>
          {c === 'mxn' ? 'Pesos (MXN)' : 'Dólares (USD)'}
        </button>
      ))}
    </div>
  )
}
