import { useEffect, useRef } from 'react'
import { HOUSE_STYLES, sampleOf } from '../lib/houseStyles'

/** The illustration style of a new tome: automatic (the Designer picks) or one of the house styles. Without a
 * plan the free ones come first and the others show what a plan unlocks. */
export function StylePicker({ value, onChange, paid }: { value: string | null; onChange: (key: string | null) => void; paid: boolean }) {
  const row = useRef<HTMLDivElement>(null)
  const styles = paid ? HOUSE_STYLES : [...HOUSE_STYLES.filter((s) => s.free), ...HOUSE_STYLES.filter((s) => !s.free)]
  useEffect(() => {  // a style picked from the landing's cards must be visible in the scrolling row
    const box = row.current
    const on = box?.querySelector<HTMLElement>('button.on')
    if (box && on && (on.offsetLeft + on.offsetWidth > box.scrollLeft + box.clientWidth || on.offsetLeft < box.scrollLeft)) {
      box.scrollTo({ left: on.offsetLeft - 60, behavior: 'smooth' })
    }
  }, [value])
  return (
    <div className="style-picker" role="radiogroup" aria-label="Estilo de ilustración" ref={row}>
      <span className="style-picker-label">Ilustración</span>
      <button type="button" role="radio" aria-checked={value === null} className={value === null ? 'on' : undefined} onClick={() => onChange(null)}>
        <span className="style-auto" aria-hidden="true">✦</span>Automático
      </button>
      {styles.map((s) => {
        const locked = !paid && !s.free
        return (
          <button key={s.key} type="button" role="radio" aria-checked={value === s.key} disabled={locked}
                  className={value === s.key ? 'on' : undefined} title={locked ? `${s.name}: con un plan` : s.desc}
                  onClick={() => onChange(s.key)}>
            <img src={sampleOf(s.key)} alt="" width={24} height={32} />{s.name}{locked && <span className="style-lock">Plan</span>}
          </button>
        )
      })}
    </div>
  )
}
