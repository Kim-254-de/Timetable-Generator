import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from '@/lib/api'

type Handler = (config: InternalAxiosRequestConfig) => { status?: number; body: unknown }

/** Routes the shared axios instance to in-test handlers keyed by "METHOD /path". */
export function fakeApi(routes: Record<string, Handler>) {
  const calls: { method: string; url: string; data: unknown; params: unknown }[] = []
  const adapter: AxiosAdapter = async (config) => {
    const method = (config.method ?? 'get').toUpperCase()
    const url = config.url ?? ''
    calls.push({ method, url, data: config.data ? JSON.parse(config.data as string) : undefined, params: config.params })
    const handler = routes[`${method} ${url}`]
    const { status = 200, body } = handler ? handler(config) : { status: 404, body: { success: false, error: { code: 'NOT_FOUND', message: 'nope' } } }
    const response: AxiosResponse = { data: body, status, statusText: String(status), headers: {}, config }
    if (status >= 400) {
      const { AxiosError } = await import('axios')
      throw new AxiosError('failed', String(status), config, null, response)
    }
    return response
  }
  api.defaults.adapter = adapter
  return calls
}

export const ok = (data: unknown) => () => ({ body: { success: true, data } })
export const fail = (status: number, code: string, message: string, details?: unknown) => () => ({
  status,
  body: { success: false, error: { code, message, details } },
})
