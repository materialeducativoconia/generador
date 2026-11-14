import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useLocation } from 'react-router'
import { api } from '../lib/apiClient'
import { track } from '../lib/track'
import { errorText } from './ErrorNote'

type Line = { role: 'user' | 'assistant'; content: string }
const HELLO: Line = { role: 'assistant', content: '¡Hola! ¿Qué te gustaría contarnos? Puede ser algo que falló, algo que te costó o una idea para mejorar.' }

/** The first adopters' feedback: a short chat where DeepSeek asks what is missing to understand the problem or the
 * idea, then writes it down for the team (/admin/opiniones). */
export function FeedbackBubble() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [lines, setLines] = useState<Line[]>([HELLO])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const list = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' }) }, [lines, busy])
  useEffect(() => { if (open) input.current?.focus() }, [open, done])

  async function send(e?: FormEvent) {
    e?.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    const next: Line[] = [...lines, { role: 'user', content: text }]
    setLines(next)
    setDraft('')
    setBusy(true)
    setError(null)
    try {
      // The greeting is the bubble's, not DeepSeek's: the conversation starts with the user's words.
      const out = await api.post<{ reply: string; done: boolean }>('/api/feedback/chat',
        { messages: next.slice(1), path: pathname })
      setLines([...next, { role: 'assistant', content: out.reply }])
      if (out.done) { setDone(true); track('feedback_done') }
    } catch (err) {
      setError(err)
      setLines(lines)
      setDraft(text)
    } finally {
      setBusy(false)
    }
  }

  function restart() {
    setLines([HELLO])
    setDone(false)
    setError(null)
  }

  return (
    <div className="fb">
      {open && (
        <section className="fb-panel" role="dialog" aria-label="Tu opinión sobre Jelyx Docs">
          <header>
            <strong>Tu opinión</strong>
            <span className="muted small">La lee el equipo</span>
            <button className="icon" onClick={() => setOpen(false)} aria-label="Cerrar">✕</button>
          </header>
          <div className="fb-lines" ref={list} aria-live="polite">
            {lines.map((l, i) => <p key={i} className={`fb-line ${l.role}`}>{l.content}</p>)}
            {busy && <p className="fb-line assistant typing" aria-label="Escribiendo"><span /><span /><span /></p>}
          </div>
          {error ? <p className="error small" role="alert">{errorText(error, 'No se pudo enviar; inténtalo de nuevo.')}</p> : null}
          {done ? (
            <div className="fb-done"><span className="muted small">Quedó anotado ✓</span>
              <button className="ghost small" onClick={restart}>Contar otra cosa</button></div>
          ) : (
            <form className="fb-form" onSubmit={send}>
              <textarea ref={input} value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} maxLength={2000}
                        placeholder="Escribe aquí…" aria-label="Tu mensaje"
                        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }} />
              <button className="primary small" type="submit" disabled={!draft.trim() || busy}>Enviar</button>
            </form>
          )}
        </section>
      )}
      <button className="fb-toggle" onClick={() => { setOpen(!open); if (!open) track('feedback_open') }}
              aria-expanded={open} aria-label={open ? 'Cerrar opinión' : 'Danos tu opinión'}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
        </svg>
        {!open && <span>Tu opinión</span>}
      </button>
    </div>
  )
}
