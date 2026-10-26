import { describe, expect, it } from 'vitest'
import { ApiError, createApiClient } from './api'

type Call = { url: string; auth: string | null }

function fakeServer(validToken: string) {
  const calls: Call[] = []
  const fetchImpl = async (url: string | URL | Request, init?: RequestInit) => {
    const auth = new Headers(init?.headers).get('Authorization')
    calls.push({ url: String(url), auth })
    if (auth !== `Bearer ${validToken}`) {
      return Response.json({ error: { code: 'unauthorized', message: 'nope' } }, { status: 401 })
    }
    return Response.json({ ok: true })
  }
  return { calls, fetchImpl: fetchImpl as typeof fetch }
}

describe('api client', () => {
  it('sends the current access token as a Bearer header', async () => {
    const server = fakeServer('t1')
    const api = createApiClient({
      fetchImpl: server.fetchImpl,
      getAccessToken: async () => 't1',
      refreshAccessToken: async () => null,
      onSessionExpired: () => {},
    })

    await expect(api.get('/api/me')).resolves.toEqual({ ok: true })
    expect(server.calls).toEqual([{ url: '/api/me', auth: 'Bearer t1' }])
  })

  it('refreshes the session and retries once when the token has expired', async () => {
    const server = fakeServer('fresh')
    const api = createApiClient({
      fetchImpl: server.fetchImpl,
      getAccessToken: async () => 'stale',
      refreshAccessToken: async () => 'fresh',
      onSessionExpired: () => {},
    })

    await expect(api.get('/api/me')).resolves.toEqual({ ok: true })
    expect(server.calls.map((c) => c.auth)).toEqual(['Bearer stale', 'Bearer fresh'])
  })

  it('gives up after one retry and reports the expired session', async () => {
    const server = fakeServer('never-issued')
    let expired = 0
    const api = createApiClient({
      fetchImpl: server.fetchImpl,
      getAccessToken: async () => 'stale',
      refreshAccessToken: async () => 'also-rejected',
      onSessionExpired: () => {
        expired++
      },
    })

    await expect(api.get('/api/me')).rejects.toMatchObject({ status: 401, code: 'unauthorized' })
    expect(server.calls).toHaveLength(2)
    expect(expired).toBe(1)
  })

  it('surfaces API errors with their code and message', async () => {
    const fetchImpl = (async () =>
      Response.json({ error: { code: 'forbidden', message: 'Esta cuenta no está activa.' } }, { status: 403 })) as typeof fetch
    const api = createApiClient({
      fetchImpl,
      getAccessToken: async () => 't',
      refreshAccessToken: async () => null,
      onSessionExpired: () => {},
    })

    const error = await api.get('/api/me').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 403, code: 'forbidden', message: 'Esta cuenta no está activa.' })
  })
})
