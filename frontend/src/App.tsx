import { QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import { queryClient } from './lib/queries'
import { AuthCallback } from './routes/AuthCallback'
import { PageEditor } from './routes/PageEditor'
import { SectionPage } from './routes/SectionPage'
import { Studio } from './routes/Studio'
import { AdminTomes } from './routes/AdminTomes'
import { AdminStyles } from './routes/AdminStyles'
import { Characters } from './routes/Characters'
import { Styles } from './routes/Styles'
import { Identities } from './routes/Identities'
import { Plan } from './routes/Plan'
import { Profile } from './routes/Profile'
import { Analytics } from './routes/Analytics'
import { AdminUsers } from './routes/AdminUsers'
import { FirstVisit, Onboarding } from './routes/Onboarding'
import { TomePage } from './routes/TomePage'
import { Welcome } from './routes/Welcome'
import { Library, LibraryPlate } from './routes/Library'
import { Book, Books } from './routes/Books'
// Remotion only loads for the team's video studio, never for teachers.
const AdminMarketing = lazy(() => import('./routes/AdminMarketing').then((m) => ({ default: m.AdminMarketing })))

const authed = (page: ReactNode) => <RequireAuth>{page}</RequireAuth>

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Welcome />} />
            <Route path="/libros" element={<Books />} />
            <Route path="/libros/:slug" element={<Book />} />
            <Route path="/laminas" element={<Library />} />
            <Route path="/laminas/:slug" element={<LibraryPlate />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/app" element={authed(<FirstVisit><Studio /></FirstVisit>)} />
            <Route path="/app/bienvenida" element={authed(<Onboarding />)} />
            <Route path="/app/tomos/:id" element={authed(<TomePage />)} />
            <Route path="/app/secciones/:id" element={authed(<SectionPage />)} />
            <Route path="/app/tomos/:id/paginas" element={authed(<PageEditor />)} />
            <Route path="/app/estilos" element={authed(<Styles />)} />
            <Route path="/app/personajes" element={authed(<Characters />)} />
            <Route path="/app/identidades" element={authed(<Identities />)} />
            <Route path="/app/plan" element={authed(<Plan />)} />
            <Route path="/app/perfil" element={authed(<Profile />)} />
            <Route path="/admin" element={authed(<AdminUsers />)} />
            <Route path="/admin/tomos" element={authed(<AdminTomes />)} />
            <Route path="/admin/estilos" element={authed(<AdminStyles />)} />
            <Route path="/admin/analytics" element={authed(<Analytics />)} />
            <Route path="/admin/marketing" element={authed(<Suspense fallback={null}><AdminMarketing /></Suspense>)} />
            <Route path="/adminpanel" element={<Navigate to="/admin" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
