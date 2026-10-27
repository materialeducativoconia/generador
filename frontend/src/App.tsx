import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import { queryClient } from './lib/queries'
import { AuthCallback } from './routes/AuthCallback'
import { SectionPage } from './routes/SectionPage'
import { Studio } from './routes/Studio'
import { TomePage } from './routes/TomePage'
import { Welcome } from './routes/Welcome'

const authed = (page: ReactNode) => <RequireAuth>{page}</RequireAuth>

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Welcome />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/app" element={authed(<Studio />)} />
            <Route path="/app/tomos/:id" element={authed(<TomePage />)} />
            <Route path="/app/secciones/:id" element={authed(<SectionPage />)} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
