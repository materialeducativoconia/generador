import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { Logo } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api, type Me } from '../lib/apiClient'
import { AUDIENCES } from '../lib/labels'
import { useMe, useSeriesList } from '../lib/queries'

type Use = NonNullable<NonNullable<Me['onboarding']>['use']>
const USES: [Use, string, string][] = [
  ['aula', 'Doy clases', 'Material para mi grupo, listo para imprimir.'],
  ['venta', 'Vendo material educativo', 'Cuadernillos y libros con mi marca.'],
  ['escuela', 'Escuela o editorial', 'Varias materias, niveles o autores.'],
  ['casa', 'Educo en casa', 'Actividades para mis hijos o alumnos particulares.'],
]
const PLAN_FOR: Record<Use, string> = { aula: 'Docente', casa: 'Docente', venta: 'Creador', escuela: 'Editorial' }
// A first tome per subject: short enough for the trial credits, concrete enough to show what the app does.
const FIRST: Record<string, string> = {
  Lectoescritura: 'Cuadernillo de lectoescritura de la vocal A: repasar, colorear, sílabas y dictado',
  Matemáticas: 'Cuadernillo de sumas hasta el 10 con dibujos para contar y problemas cortos',
  Ciencias: 'Secuencia de lecciones sobre el ciclo del agua con un experimento casero por lección',
  Inglés: 'Vocabulario en inglés de los animales: tarjetas, colorear y relacionar con su nombre',
  Historia: 'Lecciones sobre las culturas mesoamericanas con línea del tiempo y actividades',
  Geografía: 'Cuadernillo de los continentes y océanos con mapas para colorear y ubicar',
  Música: 'Método de piano para principiantes: postura, Do central, primeras melodías con la mano derecha',
  'Arte y colorear': 'Libro para colorear de animales de la granja, con el nombre de cada animal',
  'Valores y emociones': 'Cuadernillo de emociones: reconocerlas, nombrarlas y qué hacer con cada una',
}
const SUBJECTS = Object.keys(FIRST)

/** Sends a first-time user to the welcome flow before the studio. */
export function FirstVisit({ children }: { children: ReactNode }) {
  const { data: me } = useMe()
  const [params] = useSearchParams()
  if (me?.anonymous) return <VisitorHome />
  if (me && !me.anonymous && !me.onboarded && !params.get('pedido')) return <Navigate to="/app/bienvenida" replace />
  return children
}

/** A landing visitor has no studio: their preview, or the landing to make one. */
export function VisitorHome() {
  const { data: series } = useSeriesList()
  if (!series) return <p className="center muted">Cargando…</p>
  return <Navigate to={series.length ? `/app/tomos/${series[0].id}` : '/#crear'} replace />
}

export function Onboarding() {
  const { data: me } = useMe()
  return me ? <Steps me={me} /> : <p className="center muted">Cargando…</p>
}

function Steps({ me }: { me: Me }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [use, setUse] = useState<Use | null>(me.onboarding?.use ?? null)
  const [levels, setLevels] = useState<string[]>(me.onboarding?.levels ?? [])
  const [subjects, setSubjects] = useState<string[]>(me.onboarding?.subjects ?? [])
  const [author, setAuthor] = useState(me.author_name ?? me.display_name ?? '')
  const [school, setSchool] = useState(me.school ?? '')
  const finish = useMutation({
    mutationFn: (skip: boolean) => api.post<Me>('/api/me/onboarding', skip ? {} : {
      use, levels, subjects, author_name: author.trim() || null, school: school.trim() || null,
    }),
  })
  const go = async (to: string, skip = false) => {
    qc.setQueryData(['me'], await finish.mutateAsync(skip))
    navigate(to, { replace: true })
  }
  const toggle = (list: string[], set: (v: string[]) => void, v: string) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

  const audience = levels[0] ?? AUDIENCES[0]
  const ideas = (subjects.length ? subjects : ['Lectoescritura', 'Matemáticas', 'Ciencias']).slice(0, 3)
  const steps = [
    {
      title: '¿Cómo usarás Jelyx Docs?',
      body: (
        <div className="choice-grid">
          {USES.map(([key, label, hint]) => (
            <button key={key} type="button" className={`choice${use === key ? ' on' : ''}`} aria-pressed={use === key}
                    onClick={() => { setUse(key); setStep(1) }}>
              <strong>{label}</strong><span className="muted small">{hint}</span>
            </button>
          ))}
        </div>
      ),
      ready: use !== null,
    },
    {
      title: '¿Para quién y de qué?',
      body: (
        <>
          <p className="muted small">Niveles</p>
          <div className="chips">{AUDIENCES.map((a) => (
            <button key={a} type="button" className={`chip${levels.includes(a) ? ' on' : ''}`} aria-pressed={levels.includes(a)}
                    onClick={() => toggle(levels, setLevels, a)}>{a}</button>
          ))}</div>
          <p className="muted small">Materias</p>
          <div className="chips">{SUBJECTS.map((s) => (
            <button key={s} type="button" className={`chip${subjects.includes(s) ? ' on' : ''}`} aria-pressed={subjects.includes(s)}
                    onClick={() => toggle(subjects, setSubjects, s)}>{s}</button>
          ))}</div>
        </>
      ),
      ready: levels.length > 0,
    },
    {
      title: '¿Cómo firmas tu material?',
      body: (
        <div className="onb-form">
          <label className="field"><span>Elaborado por</span>
            <input value={author} maxLength={80} onChange={(e) => setAuthor(e.target.value)} placeholder="Profa. Ana Ruiz" />
          </label>
          <label className="field"><span>Escuela, institución o marca (opcional)</span>
            <input value={school} maxLength={120} onChange={(e) => setSchool(e.target.value)} />
          </label>
          <p className="muted small">Aparece en la portada de cada material. Puedes cambiarlo en tu perfil.</p>
        </div>
      ),
      ready: true,
    },
    {
      title: 'Hagamos tu primer material',
      body: (
        <>
          <p className="muted">
            {me.credits > 0
              ? <>Tienes <strong>{me.credits} créditos</strong>. </>
              : <>Tu primera vista previa es gratis: portada ilustrada, índice y una muestra de la primera sección. </>}
            Elige una idea; podrás ajustarla antes de generar.
          </p>
          <div className="choice-grid">
            {ideas.map((s) => (
              <button key={s} type="button" className="choice" disabled={finish.isPending}
                      onClick={() => void go(`/app?${new URLSearchParams({ pedido: FIRST[s] ?? `Cuadernillo de ${s}`, publico: audience })}`)}>
                <strong>{s}</strong><span className="muted small">{FIRST[s]}</span>
              </button>
            ))}
            <button type="button" className="choice" disabled={finish.isPending} onClick={() => void go('/app')}>
              <strong>Escribir mi propio tema</strong><span className="muted small">Cualquier materia, nivel o formato.</span>
            </button>
          </div>
          {use && <p className="muted small">Cuando quieras más, el plan que más te conviene es <strong>{PLAN_FOR[use]}</strong>.</p>}
        </>
      ),
      ready: true,
    },
  ]
  const current = steps[step]

  return (
    <main className="onboarding">
      <div className="onb-top">
        <span className="brand"><Logo /><span>Jelyx Docs</span></span>
        <button type="button" className="ghost small" disabled={finish.isPending} onClick={() => void go('/app', true)}>Omitir</button>
      </div>
      <ol className="onb-dots" aria-label={`Paso ${step + 1} de ${steps.length}`}>
        {steps.map((_, i) => <li key={i} className={i <= step ? 'on' : ''} />)}
      </ol>
      <h1 className="display sm">{step === 0 && me.display_name ? `Hola, ${me.display_name.split(' ')[0]}. ` : ''}{current.title}</h1>
      <div className="onb-body">{current.body}</div>
      {finish.error && <p className="error" role="alert">{errorText(finish.error, 'No pudimos guardar tus respuestas.')}</p>}
      <div className="onb-nav">
        {step > 0 && <button type="button" className="ghost" onClick={() => setStep(step - 1)}>Atrás</button>}
        {step < steps.length - 1 && (
          <button type="button" className="primary" disabled={!current.ready} onClick={() => setStep(step + 1)}>Continuar</button>
        )}
      </div>
    </main>
  )
}
