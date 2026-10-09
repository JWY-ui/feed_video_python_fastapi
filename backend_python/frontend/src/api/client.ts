import { useAuthStore } from '../stores/auth'
import { reportError } from '../utils/error-reporter'

export class ApiError extends Error {
  status: number
  payload?: unknown

  constructor(message: string, status: number, payload?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

type ApiErrorBody = { error?: string; detail?: unknown }

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

/**
 * Endpoints where a 401 is a meaningful answer in itself (wrong credentials)
 * rather than "your session expired".
 *
 * For these we must NOT replay through the refresh flow -- a mistyped password
 * would otherwise burn a refresh round-trip and then clear the tokens of a
 * session that is perfectly valid in another tab.
 */
const NO_AUTH_RETRY = new Set([
  '/account/refresh',
  '/account/login',
  '/account/register',
  '/account/changePassword',
])

type RefreshResult =
  | { status: 'refreshed'; token: string }
  | { status: 'invalid' }
  | { status: 'transient' }

let isRefreshing = false
let refreshPromise: Promise<RefreshResult> | null = null

/**
 * Single-flight refresh. Owns the "should we log the user out?" decision so no
 * caller has to guess:
 *   refreshed -> retry the request with the new token
 *   invalid   -> the refresh token is dead; tokens already cleared, session over
 *   transient -> network/5xx; the session is probably fine, DO NOT clear
 */
async function tryRefresh(): Promise<RefreshResult> {
  const auth = useAuthStore()
  // No refresh token at all: the access token is already unusable and there is
  // nothing to exchange, so the session really is over.
  if (!auth.refreshToken) {
    auth.clearTokens()
    return { status: 'invalid' }
  }
  if (isRefreshing && refreshPromise) return refreshPromise

  isRefreshing = true
  refreshPromise = (async (): Promise<RefreshResult> => {
    try {
      const res = await fetch(`${API_BASE}/account/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: auth.refreshToken, access_token: auth.token }),
      })
      // The refresh token itself was rejected -> the session is genuinely over.
      if (res.status === 401 || res.status === 403) {
        auth.clearTokens()
        return { status: 'invalid' }
      }
      // Anything else non-2xx (5xx, proxy error) is not proof the user is logged out.
      if (!res.ok) return { status: 'transient' }
      const data = await res.json()
      auth.setToken(data.token)
      return { status: 'refreshed', token: data.token as string }
    } catch {
      // Network error or timeout -- don't log out, just report failure.
      return { status: 'transient' }
    } finally {
      isRefreshing = false
    }
  })()

  return refreshPromise
}

/**
 * Refresh entry point for callers that do their own transport (the SSE stream
 * client), so they share this module's single-flight state instead of racing it.
 */
export async function refreshAccessToken(): Promise<string | null> {
  const result = await tryRefresh()
  return result.status === 'refreshed' ? result.token : null
}

async function sendWithAuth(
  path: string,
  body: BodyInit,
  baseHeaders: Record<string, string>,
): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: baseHeaders, body })

  if (res.status !== 401 || NO_AUTH_RETRY.has(path)) return res

  const refreshed = await tryRefresh()
  if (refreshed.status === 'refreshed') {
    const retryRes = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { ...baseHeaders, Authorization: `Bearer ${refreshed.token}` },
      body,
    })
    // A 401 on the retry means the freshly minted token was rejected too.
    return retryRes
  }

  // Do NOT fall through to handleResponse(res) here: res is the original 401 and
  // handleResponse would clear the tokens, signing the user out on a network blip
  // -- the exact opposite of what 'transient' means.
  if (refreshed.status === 'invalid') {
    throw new ApiError('登录状态已失效，请重新登录', 401)
  }
  const err = new ApiError('网络异常，请稍后重试', res.status, null)
  reportError(err, { path, status: res.status, phase: 'refresh' })
  throw err
}

export async function postJson<T>(path: string, body: unknown, options?: { authRequired?: boolean }): Promise<T> {
  const auth = useAuthStore()
  const token = auth.token

  if (options?.authRequired && !token) {
    throw new ApiError('需要先登录（缺少 token）', 401)
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await sendWithAuth(path, JSON.stringify(body ?? {}), headers)
  return handleResponse<T>(res, path, !NO_AUTH_RETRY.has(path))
}

export async function postForm<T>(path: string, body: FormData, options?: { authRequired?: boolean }): Promise<T> {
  const auth = useAuthStore()
  const token = auth.token

  if (options?.authRequired && !token) {
    throw new ApiError('需要先登录（缺少 token）', 401)
  }

  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await sendWithAuth(path, body, headers)
  return handleResponse<T>(res, path, !NO_AUTH_RETRY.has(path))
}

/**
 * Pull the human-readable message out of an error body.
 *
 * The backend speaks FastAPI's convention: `{"detail": "..."}`. Note that on a
 * validation error (422) `detail` is an ARRAY of per-field objects, so it can't
 * be stringified blindly -- that would surface "[object Object]".
 */
function extractMessage(data: unknown, status: number): string {
  if (data && typeof data === 'object') {
    const body = data as ApiErrorBody
    if (typeof body.error === 'string' && body.error) return body.error
    if (typeof body.detail === 'string' && body.detail) return body.detail
    if (Array.isArray(body.detail)) {
      const first = body.detail[0] as { msg?: unknown } | undefined
      if (first && typeof first.msg === 'string' && first.msg) return first.msg
    }
  }
  return `请求失败 (${status})`
}

async function handleResponse<T>(res: Response, path: string, clearOn401: boolean): Promise<T> {
  const auth = useAuthStore()
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }

  if (!res.ok) {
    if (res.status === 401 && clearOn401) auth.clearTokens()
    const apiErr = new ApiError(extractMessage(data, res.status), res.status, data)
    reportError(apiErr, { path, status: res.status })
    throw apiErr
  }

  return data as T
}
