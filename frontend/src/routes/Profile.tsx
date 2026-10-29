import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api, type Me } from '../lib/apiClient'
import { useMe } from '../lib/queries'

const LOGO_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const ROLE: Record<Me['organization']['role'], string> = { owner: 'Dueño', editor: 'Editor', viewer: 'Lector' }

/** How the user signs their material: "Elaborado por …", the school and, from Creador up, the logo. */
export function Profile() {
  const { data: me } = useMe()
  return me ? <ProfileForm me={me} /> : <AppShell><div className="skeleton" /></AppShell>
}

function ProfileForm({ me }: { me: Me }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ display_name: me.display_name ?? '', author_name: me.author_name ?? '', school: me.school ?? '' })
  const file = useRef<HTMLInputElement>(null)
  const done = (fresh: Me) => qc.setQueryData(['me'], fresh)

  const save = useMutation({ mutationFn: () => api.patch<Me>('/api/me', form), onSuccess: done })
  const upload = useMutation({
    mutationFn: async (f: File) => {
      if (!LOGO_TYPES.includes(f.type)) throw new Error('Sube un PNG, JPG o WebP.')
      const { key, upload_url } = await api.post<{ key: string; upload_url: string }>('/api/me/logo', { content_type: f.type, size: f.size })
      const put = await fetch(upload_url, { method: 'PUT', body: f, headers: { 'Content-Type': f.type } })
      if (!put.ok) throw new Error('No se pudo subir el logo.')
      return api.put<Me>('/api/me/logo', { key })
    },
    onSuccess: done,
  })
  const remove = useMutation({ mutationFn: () => api.delete('/api/me/logo'), onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }) })

  const signature = [form.author_name.trim() || form.display_name.trim(), form.school.trim()].filter(Boolean).join(' · ')
  const dirty = form.display_name !== (me.display_name ?? '') || form.author_name !== (me.author_name ?? '') || form.school !== (me.school ?? '')
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }
  const error = save.error ?? upload.error ?? remove.error

  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Perfil</p>
          <h1 className="display">Tu firma en cada material</h1>
          <p className="muted">Lo que escribas aquí aparece en la portada de tus PDF y Word nuevos.</p>
        </div>
      </section>

      <div className="profile-grid">
        <form className="panel profile-form" onSubmit={submit}>
          <label className="field"><span>Tu nombre</span>
            <input value={form.display_name} maxLength={80} required onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </label>
          <label className="field"><span>Firma («Elaborado por…»)</span>
            <input value={form.author_name} maxLength={80} placeholder={form.display_name || 'Profa. Ana Ruiz'}
                   onChange={(e) => setForm({ ...form, author_name: e.target.value })} />
          </label>
          <label className="field"><span>Escuela, institución o marca</span>
            <input value={form.school} maxLength={120} placeholder="Opcional"
                   onChange={(e) => setForm({ ...form, school: e.target.value })} />
          </label>
          <div className="profile-actions">
            <button className="primary" type="submit" disabled={!dirty || save.isPending}>{save.isPending ? 'Guardando…' : 'Guardar'}</button>
            {save.isSuccess && !dirty && <span className="muted small" role="status">Guardado</span>}
          </div>
        </form>

        <div className="panel signature-preview" aria-label="Vista previa">
          <span className="eyebrow">Así se imprime</span>
          <div className="signature-line">
            {me.plan.logo && me.organization.logo_url && <img src={me.organization.logo_url} alt="" />}
            <span>{signature ? `Elaborado por ${signature}` : 'Sin firma'}</span>
          </div>
          <div className="logo-box">
            <strong>Logo</strong>
            {me.plan.logo ? (
              <>
                <p className="muted small">PNG con fondo transparente, máx. 2 MB. Se imprime junto a tu firma.</p>
                <div className="profile-actions">
                  <input ref={file} type="file" accept={LOGO_TYPES.join(',')} hidden
                         onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = '' }} />
                  <button className="ghost small" type="button" disabled={upload.isPending} onClick={() => file.current?.click()}>
                    {upload.isPending ? 'Subiendo…' : me.organization.logo_url ? 'Cambiar logo' : 'Subir logo'}
                  </button>
                  {me.organization.logo_url && <button className="ghost small" type="button" disabled={remove.isPending} onClick={() => remove.mutate()}>Quitar</button>}
                </div>
              </>
            ) : (
              <p className="muted small">Tu logo en cada portada está disponible desde el plan <strong>Creador</strong>. <Link to="/app/plan">Ver planes</Link></p>
            )}
          </div>
        </div>
      </div>
      {error && <p className="error" role="alert">{errorText(error, error instanceof Error ? error.message : 'No se pudo guardar.')}</p>}

      <section className="panel account">
        <h2 className="h3">Cuenta</h2>
        <dl>
          <dt>Correo</dt><dd>{me.email}</dd>
          <dt>Plan</dt><dd>{me.plan.label} · {me.credits} créditos · <Link to="/app/plan">Administrar</Link></dd>
          <dt>Organización</dt><dd>{me.organization.name} · {ROLE[me.organization.role]}</dd>
          {me.plan.watermark && <><dt>Uso</dt><dd>Solo en el aula (los PDF llevan la nota «uso en el aula»)</dd></>}
        </dl>
      </section>
    </AppShell>
  )
}
