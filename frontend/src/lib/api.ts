import axios, { AxiosError } from 'axios'
import type { ApiErrorBody } from './types'

/**
 * Sign-in uses an httpOnly session cookie set by the Allocator API, so no
 * token is ever readable from JavaScript. Because the browser attaches that
 * cookie automatically, state-changing requests also carry the CSRF token the
 * API sets in the `XSRF-TOKEN` cookie, echoed back as `X-XSRF-TOKEN`.
 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  withCredentials: true,
  withXSRFToken: true,
  xsrfCookieName: 'XSRF-TOKEN',
  xsrfHeaderName: 'X-XSRF-TOKEN',
  timeout: 30_000,
})

/**
 * The API wraps every response: `{ success: true, data }` or
 * `{ success: false, error: { code, message, details } }`. The app works with
 * bare data and `{ message, code, details }` errors; the translation happens here, once.
 */
interface Envelope {
  success: boolean
  data?: unknown
  error?: { code?: string; message?: string; details?: unknown }
}
const isEnvelope = (v: unknown): v is Envelope =>
  typeof v === 'object' && v !== null && typeof (v as Envelope).success === 'boolean'

api.interceptors.response.use(
  (res) => {
    if (isEnvelope(res.data)) res.data = res.data.data ?? null
    return res
  },
  (error: unknown) => {
    if (error instanceof AxiosError && error.response && isEnvelope(error.response.data)) {
      const body = error.response.data.error
      error.response.data = {
        message: body?.message ?? 'Something went wrong.',
        code: body?.code,
        details: body?.details,
      } satisfies ApiErrorBody
    }
    throw error
  },
)

export function errorBody(err: unknown): ApiErrorBody | undefined {
  if (err instanceof AxiosError) return err.response?.data as ApiErrorBody | undefined
  return undefined
}

export function errorCode(err: unknown): string | undefined {
  return errorBody(err)?.code
}

export function errorMessage(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (err instanceof AxiosError) {
    if (err.code === 'ECONNABORTED') return 'The server took too long to respond. Please try again.'
    if (!err.response) return 'Cannot reach the server. Check your connection.'
    const body = err.response.data as ApiErrorBody | undefined
    if (body?.code && body.message) return body.message
    if (err.response.status >= 500) return fallback
    return body?.message ?? fallback
  }
  return fallback
}

export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await api.get<T>(url, { params })
  return res.data
}
