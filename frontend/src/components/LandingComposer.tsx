import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { ensureVisitorSession } from '../auth/google'
import { api } from '../lib/apiClient'
import { AUDIENCES } from '../lib/labels'
import { errorText } from './ErrorNote'
import { FREE_PREVIEW_PAGES } from '../lib/pricing'

const PAGES = Array.from({ length: FREE_PREVIEW_PAGES }, (_, i) => i + 1)  // the preview's longest tome
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined

/** The landing's request box: no account needed. The visitor becomes an anonymous user and gets the free preview
 *  (outline, illustrated cover and a sample of the first section); the studio opens on it. */
export function LandingComposer({ onStart }: { onStart: (busy: boolean) => void }) {
  const navigate = useNavigate()
  const [params] = useSearchParams()  // a topic page's "Ver mi vista previa" arrives with the request filled in
  const [request, setRequest] = useState(params.get('pedido') ?? '')
  const [audience, setAudience] = useState(AUDIENCES.includes(params.get('publico') ?? '') ? params.get('publico')! : AUDIENCES[0])
  const [pages, setPages] = useState<number | null>(null)
  const [sections, setSections] = useState<number | null>(null)
  const [captcha, setCaptcha] = useState<string | undefined>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const ready = request.trim().length >= 3 && pages !== null && sections !== null && (!SITE_KEY || !!captcha)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!ready || busy) return
    setBusy(true)
    onStart(true)
    setError(null)
    try {
      await ensureVisitorSession(captcha)
      const created = await api.post<{ series: { id: string } }>('/api/series', {
        request: request.trim(), audience, language: 'es', section_count: sections, page_count: pages,
      })
      navigate(`/app/tomos/${created.series.id}`)
    } catch (err) {
      setError(err)
      setBusy(false)
      onStart(false)
    }
  }

  return (
    <form id="crear" className="composer landing-composer" onSubmit={submit}>
      <textarea value={request} onChange={(e) => setRequest(e.target.value)} rows={3} maxLength={2000}
                placeholder="Ej.: Cuadernillo de sumas hasta el 10 con dibujos para contar…" aria-label="Describe el material" />
      <div className="composer-bar">
        <label className="select-pill"><span className="sr-only">Público</span>
          <select value={audience} onChange={(e) => setAudience(e.target.value)}>{AUDIENCES.map((a) => <option key={a}>{a}</option>)}</select>
        </label>
        <label className={`select-pill${pages === null ? ' needed' : ''}`}><span className="sr-only">Páginas de contenido</span>
          <select value={pages ?? ''} required onChange={(e) => {
            const n = Number(e.target.value)
            setPages(n)
            if (sections !== null && sections > n) setSections(n)
          }}>
            <option value="" disabled>Páginas…</option>
            {PAGES.map((n) => <option key={n} value={n}>{n} {n === 1 ? 'página' : 'páginas'}</option>)}
          </select>
        </label>
        <label className={`select-pill${sections === null ? ' needed' : ''}`}><span className="sr-only">Secciones</span>
          <select value={sections ?? ''} required onChange={(e) => setSections(Number(e.target.value))}>
            <option value="" disabled>Secciones…</option>
            {PAGES.map((n) => (
              <option key={n} value={n} disabled={pages !== null && n > pages}>{n} {n === 1 ? 'sección' : 'secciones'}</option>
            ))}
          </select>
        </label>
        <button className="primary landing-go" type="submit" disabled={!ready || busy}>
          {busy ? 'Generando…' : 'Generar'}
        </button>
      </div>
      {SITE_KEY && <Turnstile siteKey={SITE_KEY} onToken={setCaptcha} />}
      {error ? <p className="error small" role="alert">{errorText(error, error instanceof Error ? error.message : 'No pudimos crear tu vista previa.')}</p> : null}
    </form>
  )
}

declare global {
  interface Window {
    turnstile?: { render: (el: HTMLElement, opts: { sitekey: string; callback: (token: string) => void; 'expired-callback'?: () => void }) => string }
  }
}

/** Cloudflare's bot check, shown only when VITE_TURNSTILE_SITE_KEY is set (Supabase then requires its token). */
function Turnstile({ siteKey, onToken }: { siteKey: string; onToken: (t: string | undefined) => void }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const draw = () => box.current && window.turnstile?.render(box.current, {
      sitekey: siteKey, callback: onToken, 'expired-callback': () => onToken(undefined),
    })
    if (window.turnstile) { draw(); return }
    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.onload = draw
    document.head.appendChild(script)
  }, [siteKey, onToken])
  return <div ref={box} className="turnstile" />
}
