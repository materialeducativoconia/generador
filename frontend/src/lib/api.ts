export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type ApiClientDeps = {
  fetchImpl: typeof fetch
  getAccessToken: () => Promise<string | null>
  /** Asks Supabase for a new access token; null when the session can't be renewed. */
  refreshAccessToken: () => Promise<string | null>
  onSessionExpired: () => void
}

export function createApiClient({ fetchImpl, getAccessToken, refreshAccessToken, onSessionExpired }: ApiClientDeps) {
  async function send(path: string, init: RequestInit, token: string | null) {
    const headers = new Headers(init.headers)
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (init.body) headers.set('Content-Type', 'application/json')
    return fetchImpl(path, { ...init, headers })
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response = await send(path, init, await getAccessToken())

    // The access token lasts ~1 h; supabase-js usually renews it first, but a tab
    // waking from sleep can still send a stale one. Renew and retry exactly once.
    if (response.status === 401) {
      const fresh = await refreshAccessToken()
      if (fresh) response = await send(path, init, fresh)
      if (response.status === 401) onSessionExpired()
    }

    const body = response.status === 204 ? null : await response.json().catch(() => null)
    if (!response.ok) {
      const error = body?.error ?? {}
      throw new ApiError(response.status, error.code ?? 'unknown_error', error.message ?? response.statusText)
    }
    return body as T
  }

  return {
    get: <T>(path: string) => request<T>(path),
    post: <T>(path: string, data?: unknown, headers?: Record<string, string>) =>
      request<T>(path, { method: 'POST', body: JSON.stringify(data ?? {}), headers }),
    patch: <T>(path: string, data: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(data) }),
    put: <T>(path: string, data: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (path: string) => request<null>(path, { method: 'DELETE' }),
  }
}
