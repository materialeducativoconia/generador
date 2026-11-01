import type { ReactNode } from 'react'
import type { Billing } from '../lib/queries'

export type PlanInfo = Billing['plans'][number]

const PITCH: Record<string, string> = {
  docente: 'Para tu grupo: material listo para imprimir y usar en clase.',
  creador: 'Para vender tu material con tu propia marca.',
  editorial: 'Para escuelas y editoriales: varias marcas, equipo y los mejores modelos.',
}

/** The plans side by side, as pricing pages do: price, the button, then what is in (✓) and what is not (✗). */
export function PlanCards({ plans, current, action }: { plans: PlanInfo[]; current?: string; action: (p: PlanInfo) => ReactNode }) {
  return (
    <div className="plan-grid">
      {plans.map((p) => (
        <article key={p.key} className={`plan-card${p.key === current ? ' current' : ''}${p.key === 'creador' ? ' featured' : ''}`}>
          <header>
            <h3>{p.label}</h3>
            {p.key === 'creador' && <span className="plan-badge">Más elegido</span>}
          </header>
          <p className="plan-pitch">{PITCH[p.key]}</p>
          <p className="plan-price"><strong>${p.price_usd}</strong><span>USD / mes</span></p>
          <p className="plan-credits"><strong>{p.credits.toLocaleString('es-MX')}</strong> créditos al mes · ~{Math.round(p.credits / 29)} tomos de 24 páginas</p>
          <div className="plan-cta">{action(p)}</div>
          <Features plan={p} />
        </article>
      ))}
    </div>
  )
}

function Features({ plan: p }: { plan: PlanInfo }) {
  const rows: [boolean, string][] = [
    [true, `Tomos de hasta ${p.max_pages} páginas`],
    [true, 'Libro ilustrado, para colorear, fichas y métodos'],
    [true, 'PDF listo para imprimir'],
    [!p.watermark, 'Sin marca de agua'],
    [p.commercial, 'Licencia para vender lo que creas'],
    [p.word, 'Descarga en Word editable'],
    [p.print_edition, 'Edición para imprenta (KDP)'],
    [p.identities > 0, p.identities > 1 ? `${p.identities} identidades de marca` : 'Tu identidad de marca y logo'],
    [p.styles > 0, p.styles ? `${p.styles} estilos de referencia` : 'Estilos de referencia'],
    [p.premium, 'Modelos de IA premium'],
    [p.seats > 1, p.seats > 1 ? `Equipo de ${p.seats} personas` : 'Trabajo en equipo'],
    [true, `${p.concurrent} ${p.concurrent === 1 ? 'tomo' : 'tomos'} generándose a la vez`],
  ]
  return (
    <ul className="plan-features">
      {rows.map(([on, label]) => (
        <li key={label} className={on ? 'on' : 'off'}>
          <svg viewBox="0 0 16 16" aria-hidden="true">{on ? <path d="M3.5 8.5l3 3 6-7" /> : <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" />}</svg>
          <span><span className="sr-only">{on ? 'Incluye: ' : 'No incluye: '}</span>{label}</span>
        </li>
      ))}
    </ul>
  )
}
